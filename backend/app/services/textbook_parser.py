"""LLM-based textbook chapter/section recognition.

Sends extracted PDF text to an LLM (via the configured llm_client) to
identify chapters, sections, and structure, then maps them to page ranges.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)

STRUCTURE_EXTRACTION_PROMPT = """你是一位教材结构分析专家。以下是一本教材的文本内容（Markdown格式，来自PDF转换）。

请仔细分析并提取这本教材的完整章节目录结构，包括：
1. 教材的标题（如果能在文本中找到）
2. 教材的作者（如果能在文本中找到）
3. 所有章（chapter）的标题
4. 每章包含的所有节（section）的标题
5. 每节的简要学习目标（一句话描述本节要掌握的核心内容）
6. 每节建议的学习时间（estimated_minutes，整数，默认45分钟）
7. 每节涉及的核心知识点（knowledge_points，字符串列表，3-5个）

要求：
- 按照书中出现的顺序列出
- 准确识别章、节标题的编号模式（如"第一章"、"第1章"、"Chapter 1"、"1.1"等）
- 如果文本中有目录页，优先依据目录页内容
- 如果没有明确的节标题，根据内容段落主题划分出合理的节结构
- 学习目标要具体、可衡量
- 知识点应为简短的关键词或短语

输出格式为纯JSON（不要用Markdown代码块包裹）：
{{
  "title": "教材名称",
  "author": "作者",
  "chapters": [
    {{
      "title": "第1章 绪论",
      "order": 0,
      "sections": [
        {{
          "title": "1.1 基本概念",
          "goal": "理解数据结构的基本概念和分类",
          "order": 0,
          "estimated_minutes": 45,
          "knowledge_points": ["数据结构定义", "逻辑结构", "物理结构", "抽象数据类型"]
        }}
      ]
    }}
  ]
}}

如果教材内容无法识别到任何结构，返回：
{{"title": "", "author": "", "chapters": []}}

教材内容：
{text}
"""


def build_structure_from_toc(
    native_toc: list[dict[str, Any]], page_count: int
) -> dict[str, Any] | None:
    """Build a preliminary chapter/section structure from a native PDF TOC.

    Args:
        native_toc: List of [{title, page, level}, ...] from pymupdf get_toc().
        page_count: Total PDF pages.

    Returns a dict with {title, author, chapters} or None.
    """
    if not native_toc:
        return None

    chapters: list[dict] = []
    current_chapter: dict | None = None

    for entry in native_toc:
        title = entry.get("title", "").strip()
        page = entry.get("page", 1)
        level = entry.get("level", 1)

        if not title:
            continue

        if level == 1:
            # New chapter
            if current_chapter:
                # Close previous chapter's end page
                current_chapter.setdefault("end_page", page - 1)
                chapters.append(current_chapter)

            current_chapter = {
                "title": title,
                "order": len(chapters),
                "start_page": page,
                "end_page": page_count,  # will be refined
                "sections": [],
            }
        elif level >= 2 and current_chapter is not None:
            # New section within current chapter
            if current_chapter["sections"]:
                current_chapter["sections"][-1].setdefault("end_page", page - 1)

            current_chapter["sections"].append({
                "title": title,
                "order": len(current_chapter["sections"]),
                "start_page": page,
                "end_page": page_count,  # will be refined
                "estimated_minutes": 45,
                "knowledge_points": [],
                "goal": "",
            })

    # Close last chapter
    if current_chapter:
        current_chapter.setdefault("end_page", page_count)
        chapters.append(current_chapter)

    # Refine end pages: each section ends at the next section's start - 1
    for ch in chapters:
        for i, sec in enumerate(ch.get("sections", [])):
            if i + 1 < len(ch["sections"]):
                sec["end_page"] = max(sec["start_page"], ch["sections"][i + 1]["start_page"] - 1)
            else:
                sec["end_page"] = ch["end_page"]

    return {
        "title": "",
        "author": "",
        "chapters": chapters,
    }


def _call_llm_for_structure(prompt: str) -> dict[str, Any]:
    """Send the extraction prompt to the LLM and parse the JSON response.

    Uses the configured llm_client to make the call.
    """
    from app.services.llm_client import get_llm_client

    client = get_llm_client()
    messages = [
        {"role": "user", "content": prompt},
    ]

    try:
        content = client.chat(
            messages=messages,
            temperature=0.1,
            max_tokens=65536,
        )
        # chat() returns a string (the model's response text)
        if isinstance(content, dict):
            # fallback: some providers might return a dict
            content = content.get("content", "")
    except LLMClientError:
        logger.exception("LLM call failed during textbook structure extraction")
        raise

    return _parse_llm_json_response(str(content))


def _parse_llm_json_response(content: str) -> dict[str, Any]:
    """Parse the LLM's JSON response, handling markdown code block wrapping
    and truncated/incomplete JSON."""
    # Try to extract JSON from markdown code blocks (closed or unclosed)
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)(?:\n?```|$)", content, re.DOTALL)
    if json_match:
        content = json_match.group(1)

    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object boundaries
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    # ── Truncated JSON repair ──
    # The LLM response may be cut off mid-structure.
    # Try to close any open brackets / braces / quotes.
    if start >= 0:
        truncated = content[start:]
        repaired = _repair_truncated_json(truncated)
        if repaired:
            try:
                result = json.loads(repaired)
                logger.warning(
                    "LLM response was truncated — repaired JSON with %d chapters",
                    len(result.get("chapters", [])),
                )
                return result
            except json.JSONDecodeError:
                pass

    logger.error("Failed to parse LLM response as JSON: %s", content[:500])
    return {"title": "", "author": "", "chapters": []}


def _repair_truncated_json(text: str) -> str | None:
    """Attempt to repair a truncated JSON string by closing open brackets.

    Scans the text character by character, tracking open brackets/quotes,
    and appends the necessary closing characters at the end.
    """
    if not text:
        return None

    stack: list[str] = []
    in_string = False
    escape = False
    repaired = ""

    for ch in text:
        repaired += ch
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

    if not stack:
        return None  # Nothing to repair — brackets were balanced

    # Close string first, then brackets (inner → outer)
    if in_string:
        repaired += '"'

    # Close remaining open brackets in reverse order
    for bracket in reversed(stack):
        if bracket == "{":
            repaired += "}"
        elif bracket == "[":
            repaired += "]"

    return repaired


def _map_chapters_to_pages(
    chapters: list[dict],
    page_texts: list[dict[str, Any]],
) -> list[dict]:
    """Refine chapter/section page ranges by matching titles against page text.

    When the LLM doesn't know page numbers, we scan the per-page text
    to find where each chapter/section title first appears.
    Falls back to proportional distribution when matching fails.
    """
    total_pages = len(page_texts)
    if not page_texts or total_pages == 0:
        return chapters

    for ch in chapters:
        ch_title = ch.get("title", "")
        # Try exact match first, then try first meaningful part of the title
        found_page = None
        for pt in page_texts:
            pt_content = pt.get("content", "")
            if ch_title and ch_title in pt_content:
                found_page = pt.get("page_number")
                break

        # Fallback: try matching just the chapter number prefix (e.g. "1 " or "Chapter 1")
        if found_page is None and ch_title:
            prefix_match = re.match(r"^[\d]+[\s\.]", ch_title)
            if prefix_match:
                prefix = prefix_match.group()
                for pt in page_texts:
                    if prefix in pt.get("content", ""):
                        found_page = pt.get("page_number")
                        break

        if found_page is not None:
            ch["start_page"] = found_page

        for sec in ch.get("sections", []):
            sec_title = sec.get("title", "")
            found_sec_page = None
            for pt in page_texts:
                if sec_title and sec_title in pt.get("content", ""):
                    found_sec_page = pt.get("page_number")
                    break

            # Fallback: try section number prefix
            if found_sec_page is None and sec_title:
                prefix_match = re.match(r"^[\d]+\.[\d]+", sec_title)
                if prefix_match:
                    prefix = prefix_match.group()
                    for pt in page_texts:
                        if prefix in pt.get("content", ""):
                            found_sec_page = pt.get("page_number")
                            break

            if found_sec_page is not None:
                sec["start_page"] = found_sec_page

    # ── Fill missing page numbers with proportional distribution ──
    _fill_missing_page_numbers(chapters, total_pages)

    # Recalculate end pages
    for ch in chapters:
        ch_start = ch.get("start_page", 1)
        sections = ch.get("sections", [])
        for i, sec in enumerate(sections):
            sec_start = sec.get("start_page", ch_start)
            if i + 1 < len(sections):
                sec["end_page"] = max(sec_start, sections[i + 1].get("start_page", sec_start) - 1)
            else:
                sec["end_page"] = max(sec_start, ch.get("end_page", min(sec_start + 10, total_pages)))

        if sections:
            ch["start_page"] = sections[0].get("start_page", ch_start)
            ch["end_page"] = sections[-1].get("end_page", ch_start + 10)
        else:
            ch.setdefault("start_page", ch_start)
            ch.setdefault("end_page", min(ch_start + 10, total_pages))

    return chapters


def _fill_missing_page_numbers(chapters: list[dict], total_pages: int) -> None:
    """Distribute pages proportionally to chapters/sections that lack page numbers.

    Chapters without page data get an equal share.  If ALL chapters share
    the same start_page (common with broken PDF TOCs), they are treated as
    unknown and redistributed evenly.
    """
    if total_pages <= 0 or not chapters:
        return

    # Detect chapters with plausible page numbers
    has_page = [ch for ch in chapters if ch.get("start_page", 0) > 0]
    if has_page:
        unique_starts = {ch.get("start_page") for ch in has_page}
        # If all known chapters start at the same page, the TOC is broken —
        # treat all as unknown so they get redistributed
        if len(unique_starts) <= 1 and len(chapters) > 1:
            for ch in chapters:
                ch.pop("start_page", None)
                ch.pop("end_page", None)
            has_page = []

    unknown_chapters = [ch for ch in chapters if not ch.get("start_page")]

    if unknown_chapters:
        share = total_pages // len(chapters)
        current_start = 1
        for ch in chapters:
            ch["start_page"] = current_start
            ch["end_page"] = min(current_start + share - 1, total_pages)
            current_start = ch["end_page"] + 1
        # Fix last chapter to reach total_pages
        if chapters:
            chapters[-1]["end_page"] = total_pages

    # Distribute pages within each chapter's sections
    for ch in chapters:
        sections = ch.get("sections", [])
        if not sections:
            continue

        ch_start = ch.get("start_page", 1)
        ch_end = ch.get("end_page", total_pages)
        ch_pages = max(1, ch_end - ch_start + 1)

        sections_without_page = [s for s in sections if not s.get("start_page")]
        if not sections_without_page:
            continue

        sec_share = max(1, ch_pages // len(sections))
        current_page = ch_start
        for i, sec in enumerate(sections):
            if not sec.get("start_page"):
                sec["start_page"] = current_page
            if i < len(sections) - 1:
                current_page = sec.get("start_page", current_page) + sec_share
                current_page = min(current_page, ch_end)
        # Last section ends at chapter end
        sections[-1]["end_page"] = ch_end


def extract_textbook_structure(
    page_texts: list[dict[str, Any]],
    native_toc: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Extract textbook chapter/section structure from page texts.

    Args:
        page_texts: List of [{page_number, content, page_label}, ...]
        native_toc: Optional native PDF TOC from pymupdf get_toc().

    Returns:
        Dict with {title, author, chapters: [{title, order, start_page,
        end_page, sections: [{title, order, start_page, end_page,
        estimated_minutes, knowledge_points}]}]}
    """
    page_count = len(page_texts)
    result: dict[str, Any] = {"title": "", "author": "", "chapters": []}

    # Strategy 1: Use native PDF TOC if available
    if native_toc:
        toc_result = build_structure_from_toc(native_toc, page_count)
        if toc_result and toc_result.get("chapters"):
            logger.info("Used native PDF TOC: %d chapters", len(toc_result["chapters"]))
            result = toc_result

    # Strategy 2: LLM-based extraction (if no native TOC or TOC was empty)
    if not result.get("chapters"):
        full_text_parts = []
        for pt in page_texts:
            full_text_parts.append(f"--- Page {pt.get('page_number', '?')} ---\n{pt.get('content', '')}")
        full_text = "\n\n".join(full_text_parts)

        max_chars = settings.textbook_max_parse_chars
        if len(full_text) > max_chars:
            head_chars = int(max_chars * 0.6)
            tail_chars = max_chars - head_chars
            remaining = full_text[head_chars:]
            step = max(1, len(remaining) // (tail_chars // 500))
            sampled = "".join(
                remaining[i : i + 500] for i in range(0, len(remaining), step)
            )[:tail_chars]
            truncated_text = full_text[:head_chars] + "\n\n[...文本已截断...]\n\n" + sampled
        else:
            truncated_text = full_text

        prompt = STRUCTURE_EXTRACTION_PROMPT.format(text=truncated_text)
        try:
            llm_result = _call_llm_for_structure(prompt)
            if llm_result.get("title"):
                result["title"] = llm_result["title"]
            if llm_result.get("author"):
                result["author"] = llm_result["author"]
            if llm_result.get("chapters"):
                result["chapters"] = llm_result["chapters"]
        except Exception:
            logger.exception("LLM structure extraction failed")

    # ── Post-processing (runs for both paths) ─────────────────────────
    chapters = result.get("chapters", [])
    if chapters:
        # Map LLM chapters to page numbers + fill missing page numbers
        # (native TOC already has page numbers, but _map_chapters_to_pages
        #  will only update chapters where start_page is missing)
        result["chapters"] = _map_chapters_to_pages(chapters, page_texts)

        # Ensure every chapter has at least one section
        for ch in result["chapters"]:
            if not ch.get("sections"):
                ch_start = ch.get("start_page", 1)
                ch_end = ch.get("end_page", page_count)
                ch["sections"] = [{
                    "title": ch.get("title", ""),
                    "order": 0,
                    "start_page": ch_start,
                    "end_page": ch_end,
                    "estimated_minutes": 45,
                    "knowledge_points": [],
                    "goal": "",
                }]

        # Assign stable IDs
        for ch in result["chapters"]:
            ch_idx = ch.get("order", 0)
            ch.setdefault("chapter_id", f"ch_{ch_idx:02d}")
            for sec in ch.get("sections", []):
                sec_idx = sec.get("order", 0)
                sec.setdefault("section_id", f"{ch['chapter_id']}_sec_{sec_idx:02d}")

    chapter_count = len(result.get("chapters", []))
    section_count = sum(len(ch.get("sections", [])) for ch in result.get("chapters", []))
    logger.info(
        "Textbook structure: %d chapters, %d sections, title=%s",
        chapter_count, section_count, result.get("title", "?"),
    )
    return result
