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

STRUCTURE_EXTRACTION_PROMPT = """你是一位教材结构分析专家，专门从OCR识别后的PDF文本中提取章节目录结构。

文本中以 "--- Page N ---" 标记了每一页的起始位置。N 是**物理页码**（从第1页开始计数，封面是第1页）。这些页码标记是你判断章节起始/结束位置的**唯一权威依据**。

## 一、标题编号格式识别

中文教材的章、节标题可能使用多种编号体系。请首先通读文本，识别出**本书实际使用**的编号规律，然后一致地应用它。

常见编号格式（非穷举，应以实际文本为准）：
- 阿拉伯数字：第1章、1.、1.1、1.1.1、1-1、1·1
- 中文数字：第一章、一、第一节、一）
- 全角标点：第１章、１．１（全角数字和全角句号）
- 特殊编号：（一）、一、、§1、§1.1、第一篇、第1部分、Unit 1、Part I
- 罗马数字：I.、II.、III.
- 无编号标题：仅有文字标题，无数字前缀（常见于某些教材的引言章）

**重要**：一本教材内部的标题编号体系是一致的。如果发现多种编号混用，应优先选择出现频率最高、最有规律的模式，并统一使用它来划分结构。

## 二、章节边界与页码标注

### 2.1 基本规则
- 章的 start_page 是该章正文标题**首次出现**的物理页码（"--- Page N ---" 中的 N 值）
- 章的 end_page 是下一章标题出现的那一页
- 节的 start_page 是该节标题**首次出现**的物理页码；end_page 是下一节标题出现的那一页
- 一个章节的正文内容可能从前一页的末尾就已经开始，也可能在一页的中间结束——**start_page 是标题所在的页号**

### 2.2 顺序约束（极其重要）
- **同一章内的各小节必须按照页码递增顺序排列**。第1.2节的 start_page 必须 ≥ 第1.1节的 start_page；第1.3节 ≥ 第1.2节；以此类推。
- **后面小节的起始页码绝对不能小于前面小节的起始页码**。如果你发现1.3节出现在比1.2节更早的页码，说明你判断错了。
- 一章内不同小节的 start_page 通常是不同的。只有在极少数情况下（如两节标题恰好挤在同一页），相邻两节才共享同一个 start_page。**绝不能让一章的所有小节都从同一页开始**。
- 如果你无法从文本中确定某个小节的起始页码，请将该 start_page 设为 0，不要编造一个数字。

### 2.3 与目录页的关系
- 如果文本中有目录页（通常在前几页，密集列出多个章节标题），请参考目录页了解全书结构
- 但 start_page **必须指向正文实际所在的页码**，不要指向目录页
- 目录页中标注的页码可能是印刷页码（如"第15页"），它和 "--- Page N ---" 中的 N 值可能不一致。请始终以 "--- Page N ---" 中的物理页码为准

## 三、OCR识别错误处理（重要）

本教材文本可能由OCR（光学字符识别）从影印本/扫描件转换而来。OCR输出**必然存在错误**。请在分析时主动识别并纠正以下常见错误：

### 3.1 形近字混淆
OCR极易混淆以下字形相近的汉字（仅列举高频错误）：
- 曰 → 日（"子曰"误识为"子日"）
- 未 → 末（"未来"误识为"末来"）
- 已 → 己 / 巳（"已经"误识为"己经"）
- 人 → 入 / 八（"人工智能"误识为"人工智入能"）
- 干 → 千（"骨干"误识为"骨千"）
- 土 → 士（"博士"误识为"博土"）
- 牛 → 午（"牛顿"误识为"午顿"）
- 本 → 木（"本章"误识为"木章"）
- 大 → 太（"大学"误识为"太学"）
- 天 → 夫（"今天"误识为"今夫"）
- 元 → 无（"单元"误识为"单无"）
- 名 → 各（"名词"误识为"各词"）

### 3.2 字符粘连与拆分
- "好"可能被识别为"女子"
- "本章"可能被识别为"木 章"（中间多了空格）
- 连续的汉字可能被错误地插入空格或标点符号
- 数学符号和公式极易出错：∑→E, ∫→f, ∞→oo, √→V

### 3.3 纠正策略
1. **语义优先**：当OCR输出在语义上不通顺时，优先根据上下文推断正确的文字
2. **术语一致**：同一专业术语在全书中的写法应当一致。如果某处出现了不合理的变体，应纠正为正确的术语
3. **章节标题校对**：章、节的标题是最重要的结构信息。如果标题看起来不合理（如"木章"、单个不完整的字），请根据上下文修正
4. **页码序列可靠**：页码标记 "--- Page N ---" 由系统生成，是可靠的。如果标题文字与页码序列存在矛盾，优先信任页码序列

## 四、非教学内容过滤

请**不要**将以下内容作为章或节输出：
- 封面、书名页、版权页
- 目录页、图表目录
- 前言、序言、致谢、导读、使用说明
- 附录、索引、参考文献、习题答案
- 后记、结语、跋

## 五、核心规则（必须严格遵守）

### 5.1 完整性 — 不得遗漏
- **必须提取每一章下的全部小节**。如果某章有5个小节，你必须输出5个小节；有10个就必须输出10个。不得合并、不得跳过、不得只输出"代表性"的小节。
- 仔细扫描全文。即使某些小节的标题在OCR后不太清晰，也请尽力识别并输出。如果一节只有标题和很少的正文内容，它仍是一个独立的小节，不应被合并到相邻小节中。
- 如果某章没有显式的小节标题，你可以根据段落主题合理划分。但如果有显式的小节标题（无论编号格式如何），必须全部提取。

### 5.2 标题保真 — 使用原文
- 章、节的标题必须**严格使用教材原文中实际出现的文字**。不要翻译、不要改写、不要总结、不要润色。
- OCR纠错仅限修正**明显的单一错字**（如"木章"→"本章"），不得修改标题的措辞、顺序或含义。
- 如果原文是中文标题，输出中文；原文是英文，输出英文。不要做任何语言转换。
- 如果原文标题包含标点符号、括号、引号等，请原样保留。

### 5.3 学习目标与知识点
- 每节的 goal 请用一句话概括本节要掌握的核心内容。语言精炼但具体可衡量。
- knowledge_points 为 3-5 个简短关键词或短语，提取自本节文本的实际内容。

## 六、需要提取的信息

1. 教材标题（仅纠OCR错字，不改写）
2. 教材作者（仅纠OCR错字）
3. 所有章——每章包含其下全部小节（complete list, no omissions）
4. 每章/节的 start_page 和 end_page
5. 每节 goal（一句话学习目标）
6. 每节 estimated_minutes（整数，默认45）
7. 每节 knowledge_points（3-5个短语）

## 七、输出格式

纯JSON（不要用Markdown代码块包裹）。注意 chapters 数组中必须包含该章的全部 sections，不得省略任何一个：

{{
  "title": "教材名称（仅纠OCR错字）",
  "author": "作者名",
  "chapters": [
    {{
      "title": "第1章 绪论",
      "order": 0,
      "start_page": 15,
      "end_page": 42,
      "sections": [
        {{
          "title": "1.1 基本概念",
          "goal": "理解数据结构的基本概念和分类",
          "order": 0,
          "start_page": 15,
          "end_page": 23,
          "estimated_minutes": 45,
          "knowledge_points": ["数据结构定义", "逻辑结构", "物理结构"]
        }},
        {{
          "title": "1.2 算法分析",
          "goal": "掌握时间复杂度和空间复杂度的分析方法",
          "order": 1,
          "start_page": 24,
          "end_page": 35,
          "estimated_minutes": 50,
          "knowledge_points": ["时间复杂度", "空间复杂度", "大O记号"]
        }},
        {{
          "title": "1.3 抽象数据类型",
          "goal": "理解ADT的概念及其在程序设计中的作用",
          "order": 2,
          "start_page": 36,
          "end_page": 42,
          "estimated_minutes": 40,
          "knowledge_points": ["抽象数据类型", "封装", "接口与实现分离"]
        }}
      ]
    }}
  ]
}}

如果无法识别任何结构，返回：
{{"title": "", "author": "", "chapters": []}}

教材文本：
{text}
"""


# TOC entries whose titles match these patterns are skipped (not real content chapters)
_NON_CONTENT_TITLE_PATTERNS = [
    r"^[cC]over",           # Cover
    r"^[fF]ront",           # Front matter
    r"^[tT]itle\s*[pP]age", # Title page
    r"^[cC]opyright",       # Copyright page
    r"^[dD]edication",      # Dedication
    r"^(前言|序[言言]?|序$)",   # Preface (Chinese)
    r"^(前言|序言|序$)",       # Preface variants
    r"^[pP]reface",         # Preface (English)
    r"^[aA]cknowledg",      # Acknowledgements
    r"^(目\s*录|目次)$",       # Table of Contents (Chinese)
    r"^[tT]able\s*[oO]f\s*[cC]ontents",  # TOC (English)
    r"^[cC]ontents$",       # Contents
    r"^[iI]ntroduction",    # Introduction (sometimes just intro to the book, not a chapter)
    r"^(导读|本书|关于|使用说明|编写|编者)",  # Guide / about / usage
    r"^(附录|Appendix|索引|Index|参考文献|Reference|Bibliography)",  # Back matter
    r"^附录\s*[A-Za-z]*",     # Appendix A, B, etc.
    r"^参考答案",              # Answer key
    r"^习题.*答案",            # Exercise answers
    r"^(后记|结语|跋|写在最后)",  # Afterword / postscript
    r"^[rR]eference[s]?\s*$", # References
]


def _is_content_chapter(title: str) -> bool:
    """Return True if the title looks like a real content chapter (not front/back matter)."""
    for pattern in _NON_CONTENT_TITLE_PATTERNS:
        if re.search(pattern, title):
            return False
    return True


def build_structure_from_toc(
    native_toc: list[dict[str, Any]], page_count: int
) -> dict[str, Any] | None:
    """Build a preliminary chapter/section structure from a native PDF TOC.

    Non-content entries (cover, preface, TOC itself, index, etc.) are
    filtered out so only real chapters appear in the learning path.

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
            # Close previous chapter
            if current_chapter:
                current_chapter.setdefault("end_page", page - 1)
                if _is_content_chapter(current_chapter.get("title", "")):
                    chapters.append(current_chapter)
                else:
                    logger.debug("Skipping non-content TOC entry: %s", current_chapter.get("title"))

            current_chapter = {
                "title": title,
                "order": len(chapters),  # order counts only kept chapters
                "start_page": page,
                "end_page": page_count,
                "sections": [],
            }
        elif level >= 2 and current_chapter is not None:
            if not _is_content_chapter(title):
                continue  # skip non-content sections

            if current_chapter["sections"]:
                current_chapter["sections"][-1].setdefault("end_page", page - 1)

            current_chapter["sections"].append({
                "title": title,
                "order": len(current_chapter["sections"]),
                "start_page": page,
                "end_page": page_count,
                "estimated_minutes": 45,
                "knowledge_points": [],
                "goal": "",
            })

    # Close last chapter
    if current_chapter:
        current_chapter.setdefault("end_page", page_count)
        if _is_content_chapter(current_chapter.get("title", "")):
            chapters.append(current_chapter)

    if not chapters:
        logger.warning("Native TOC had entries but none passed the content filter")
        return None

    # Fix orders after filtering
    for i, ch in enumerate(chapters):
        ch["order"] = i

    # Refine end pages: each section shares its boundary page with the next section.
    # When a chapter/section boundary falls mid-page, both adjacent sections
    # include the shared page so the user can always read the full content.
    for ch in chapters:
        for i, sec in enumerate(ch.get("sections", [])):
            if i + 1 < len(ch["sections"]):
                sec["end_page"] = ch["sections"][i + 1]["start_page"]
            else:
                sec["end_page"] = ch["end_page"]

    # Refine chapter end pages: share boundary pages with next chapter
    for i, ch in enumerate(chapters):
        if i + 1 < len(chapters):
            ch["end_page"] = chapters[i + 1]["start_page"]
        else:
            ch["end_page"] = page_count

    logger.info(
        "Native TOC: %d entries → %d content chapters kept (%d filtered out)",
        len(native_toc),
        len(chapters),
        len(native_toc) - len(chapters),
    )

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


def _detect_toc_end_page(
    chapters: list[dict], page_texts: list[dict[str, Any]]
) -> int:
    """Estimate the last page of the table of contents.

    Strategy: find the earliest page where MULTIPLE chapter/section titles
    are all found.  A TOC page typically contains many titles densely packed;
    a real content page usually mentions only one or two.

    Returns 0 if no clear TOC region is detected.
    """
    if not page_texts or not chapters:
        return 0

    # Collect all distinct title strings we might find
    titles_to_check: list[str] = []
    for ch in chapters:
        titles_to_check.append(ch.get("title", ""))
        for sec in ch.get("sections", []):
            titles_to_check.append(sec.get("title", ""))

    titles_to_check = [t for t in titles_to_check if len(t) >= 3]  # skip empty / tiny
    if not titles_to_check:
        return 0

    # Score each page: how many titles appear on it
    toc_end = 0
    for pt in page_texts:
        page_num = pt.get("page_number", 0)
        content = pt.get("content", "")
        matches = sum(1 for t in titles_to_check if t in content)
        # A page with 3+ title matches is almost certainly a TOC page
        if matches >= 3:
            toc_end = max(toc_end, page_num)

    # Safety: TOC is rarely longer than 10 pages in practice
    return min(toc_end, 10)


def _map_chapters_to_pages(
    chapters: list[dict],
    page_texts: list[dict[str, Any]],
) -> list[dict]:
    """Refine chapter/section page ranges by matching titles against page text.

    Key behaviours:
    - TOC pages are detected and SKIPPED during matching — otherwise every
      title matches the table-of-contents pages first, producing page numbers
      that are 2-3 pages too low.
    - Chapters/sections that already have plausible page numbers (e.g. from a
      native PDF TOC) are NOT overwritten.  "Plausible" means > the TOC
      region boundary.
    - Falls back to proportional distribution when matching fails.
    """
    total_pages = len(page_texts)
    if not page_texts or total_pages == 0:
        return chapters

    toc_end = _detect_toc_end_page(chapters, page_texts)
    if toc_end > 0:
        logger.info("Detected TOC region: pages 1-%d — skipping during title matching", toc_end)

    for ch in chapters:
        ch_title = ch.get("title", "")
        ch_existing = ch.get("start_page", 0)

        # Preserve plausible native-TOC page numbers (skip TOC pages: > toc_end)
        if ch_existing > toc_end:
            # Native TOC already gave us a valid page — don't touch it
            pass
        else:
            found_page = None
            for pt in page_texts:
                page_num = pt.get("page_number", 0)
                if page_num <= toc_end:
                    continue  # skip TOC pages
                pt_content = pt.get("content", "")
                if ch_title and ch_title in pt_content:
                    found_page = page_num
                    break

            # Fallback: try matching just the chapter number prefix
            if found_page is None and ch_title:
                prefix_match = re.match(r"^[\d]+[\s\.]", ch_title)
                if prefix_match:
                    prefix = prefix_match.group()
                    for pt in page_texts:
                        if pt.get("page_number", 0) <= toc_end:
                            continue
                        if prefix in pt.get("content", ""):
                            found_page = pt.get("page_number")
                            break

            if found_page is not None:
                ch["start_page"] = found_page

        # ── Match sections within this chapter ──────────────────────
        for sec in ch.get("sections", []):
            sec_title = sec.get("title", "")
            sec_existing = sec.get("start_page", 0)

            if sec_existing > toc_end:
                # Already has a valid non-TOC page number
                continue

            found_sec_page = None
            for pt in page_texts:
                page_num = pt.get("page_number", 0)
                if page_num <= toc_end:
                    continue
                if sec_title and sec_title in pt.get("content", ""):
                    found_sec_page = page_num
                    break

            # Fallback: try section number prefix
            if found_sec_page is None and sec_title:
                prefix_match = re.match(r"^[\d]+\.[\d]+", sec_title)
                if prefix_match:
                    prefix = prefix_match.group()
                    for pt in page_texts:
                        if pt.get("page_number", 0) <= toc_end:
                            continue
                        if prefix in pt.get("content", ""):
                            found_sec_page = pt.get("page_number")
                            break

            if found_sec_page is not None:
                sec["start_page"] = found_sec_page

    # ── Fill missing page numbers with proportional distribution ──
    _fill_missing_page_numbers(chapters, total_pages)

    # Recalculate end pages — share boundary pages with next section
    for ch in chapters:
        ch_start = ch.get("start_page", 1)
        sections = ch.get("sections", [])
        for i, sec in enumerate(sections):
            sec_start = sec.get("start_page", ch_start)
            if i + 1 < len(sections):
                sec["end_page"] = sections[i + 1].get("start_page", sec_start)
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


def _refine_section_pages(
    chapters: list[dict],
    page_texts: list[dict[str, Any]],
) -> None:
    """Refine section start pages by matching section numbers in full page text.

    Only searches WITHIN each chapter's known page range — this is a
    localized, high-precision search, unlike the old global title matching.

    Section number patterns: "1.2", "3.4.1", "§2.3", etc.
    """
    if not page_texts:
        return

    # Build a page-number → full-text lookup for efficient access
    page_map: dict[int, str] = {}
    for pt in page_texts:
        pn = pt.get("page_number", 0)
        if pn > 0:
            page_map[pn] = pt.get("content", "")

    for ch in chapters:
        ch_start = ch.get("start_page", 1)
        ch_end = ch.get("end_page", len(page_texts))

        # Determine the chapter number prefix (e.g. "1." for chapter 1)
        ch_title = ch.get("title", "")
        ch_num_match = re.match(r"^[\s\D]*(\d+)", ch_title)
        if not ch_num_match:
            continue
        ch_num = ch_num_match.group(1)

        sections = ch.get("sections", [])
        if len(sections) <= 1:
            continue  # single-section chapter — nothing to refine

        # For each section, try to find its number pattern in the full
        # page text within the chapter's page range.
        refined_count = 0
        for sec in sections:
            sec_title = sec.get("title", "")
            # Extract section number patterns: "1.2", "3.4.1", "§2.3"
            patterns = []
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)", sec_title)
            if m:
                patterns.append(m.group(1))
            # Also try the chapter-number.section pattern
            m2 = re.search(rf"\b{re.escape(ch_num)}\.(\d+)\b", sec_title)
            if m2:
                patterns.append(m2.group(0))

            if not patterns:
                continue

            found_page = None
            for page_num in range(ch_start, ch_end + 1):
                content = page_map.get(page_num, "")
                if not content:
                    continue
                for pat in patterns:
                    if pat in content:
                        found_page = page_num
                        break
                if found_page is not None:
                    break

            if found_page is not None and found_page >= ch_start:
                sec["start_page"] = found_page
                refined_count += 1

        if refined_count > 0:
            logger.debug(
                "Refined %d/%d section pages in chapter '%s' (pages %d-%d)",
                refined_count, len(sections), ch_title, ch_start, ch_end,
            )


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
    has_native_toc = False

    # ═══════════════════════════════════════════════════════════════════
    # Strategy 1: Native PDF TOC (authoritative page numbers)
    # ═══════════════════════════════════════════════════════════════════
    if native_toc:
        toc_result = build_structure_from_toc(native_toc, page_count)
        if toc_result and toc_result.get("chapters"):
            logger.info(
                "Using native PDF TOC: %d chapters (page numbers are authoritative)",
                len(toc_result["chapters"]),
            )
            result = toc_result
            has_native_toc = True

    # ═══════════════════════════════════════════════════════════════════
    # Strategy 2: LLM-based extraction (no native TOC)
    # ═══════════════════════════════════════════════════════════════════
    if not result.get("chapters"):
        # ── Build a per-page digest so the LLM can see ALL page markers ──
        # Each page contributes its first N chars.  Section/chapter headings
        # almost always appear near the top of a page, so the leading portion
        # reliably captures structural information.
        max_chars = settings.textbook_max_parse_chars
        prompt_overhead = 5000  # reserve for the expanded prompt template
        available = max(1, max_chars - prompt_overhead)
        pages_count = len(page_texts)

        # Per-page budget — never drop below 250 chars so section headings
        # on later pages remain visible to the LLM.
        chars_per_page = max(250, available // pages_count)

        digest_parts: list[str] = []
        for pt in page_texts:
            page_num = pt.get("page_number", "?")
            content = pt.get("content", "")
            snippet = content[:chars_per_page]
            digest_parts.append(f"--- Page {page_num} ---\n{snippet}")

        digest_text = "\n\n".join(digest_parts)

        # If digest still exceeds budget, use larger snippets for early pages
        # (where TOC + early chapters live) and smaller for later ones.
        if len(digest_text) > available:
            logger.info(
                "Digest too long (%d chars) — reducing later-page snippets",
                len(digest_text),
            )
            early_count = max(1, pages_count // 3)
            remaining_for_late = max(100, available - early_count * chars_per_page)
            # Late pages still get at least 150 chars — enough for a section heading
            late_chars = max(150, remaining_for_late // max(1, pages_count - early_count))

            digest_parts = []
            for i, pt in enumerate(page_texts):
                page_num = pt.get("page_number", "?")
                content = pt.get("content", "")
                limit = chars_per_page if i < early_count else late_chars
                snippet = content[:limit]
                digest_parts.append(f"--- Page {page_num} ---\n{snippet}")
            digest_text = "\n\n".join(digest_parts)

        logger.info(
            "LLM digest: %d pages, ~%d chars/page, total %d chars (budget=%d)",
            pages_count, chars_per_page, len(digest_text), max_chars,
        )

        prompt = STRUCTURE_EXTRACTION_PROMPT.format(text=digest_text)
        try:
            llm_result = _call_llm_for_structure(prompt)
            if llm_result.get("title"):
                result["title"] = llm_result["title"]
            if llm_result.get("author"):
                result["author"] = llm_result["author"]
            if llm_result.get("chapters"):
                result["chapters"] = llm_result["chapters"]
                logger.info(
                    "LLM extracted %d chapters — will map titles to pages",
                    len(llm_result["chapters"]),
                )
        except Exception:
            logger.exception("LLM structure extraction failed")

    # ═══════════════════════════════════════════════════════════════════
    # Post-processing — shared by both paths
    # ═══════════════════════════════════════════════════════════════════
    chapters = result.get("chapters", [])
    if not chapters:
        return result

    # ── Validate and clip page numbers ──────────────────────────────
    for ch in chapters:
        ch_sp = ch.get("start_page", 0)
        if not isinstance(ch_sp, int) or ch_sp < 1 or ch_sp > page_count:
            ch["start_page"] = 0  # mark as unknown
        ch_ep = ch.get("end_page", 0)
        if not isinstance(ch_ep, int) or ch_ep < 1 or ch_ep > page_count:
            ch["end_page"] = 0

        for sec in ch.get("sections", []):
            sp = sec.get("start_page", 0)
            if not isinstance(sp, int) or sp < 1 or sp > page_count:
                sec["start_page"] = 0
            ep = sec.get("end_page", 0)
            if not isinstance(ep, int) or ep < 1 or ep > page_count:
                sec["end_page"] = 0

    # ── Sanity-check section ordering within each chapter ───────────
    # The LLM sometimes assigns all sections the same start_page
    # (the chapter's first page) or puts later sections at earlier pages.
    # Detect and fix these so _fill_missing_page_numbers can interpolate.
    for ch in chapters:
        ch_start = ch.get("start_page", 0)
        sections = ch.get("sections", [])
        if len(sections) <= 1:
            continue

        # Sort sections by their declared order (not by page — the page
        # values are what we're trying to fix).
        sorted_secs = sorted(sections, key=lambda s: s.get("order", 0))

        # Detect: all sections share the same start_page (common LLM error)
        unique_pages = {
            s.get("start_page", 0)
            for s in sorted_secs
            if s.get("start_page", 0) > 0
        }
        if len(unique_pages) == 1 and len(sorted_secs) > 1:
            sole_page = next(iter(unique_pages))
            logger.warning(
                "All %d sections in chapter '%s' share start_page=%d — keeping only first",
                len(sorted_secs), ch.get("title", "?"), sole_page,
            )
            # Keep only the first section's page; mark the rest as unknown
            # so _fill_missing_page_numbers distributes them properly.
            for i, sec in enumerate(sorted_secs):
                if i > 0:
                    sec["start_page"] = 0
                    sec["end_page"] = 0

        # Detect: any section's start_page is BEFORE the previous section's
        prev_page = 0
        for sec in sorted_secs:
            sp = sec.get("start_page", 0)
            if sp > 0:
                if sp < prev_page:
                    logger.warning(
                        "Section '%s' start_page=%d < previous=%d — marking as unknown",
                        sec.get("title", "?"), sp, prev_page,
                    )
                    sec["start_page"] = 0
                    sec["end_page"] = 0
                else:
                    prev_page = sp

        # Detect: section start_page outside chapter bounds
        ch_start_val = ch.get("start_page", 0)
        if ch_start_val > 0:
            for sec in sorted_secs:
                sp = sec.get("start_page", 0)
                if sp > 0 and sp < ch_start_val:
                    logger.warning(
                        "Section '%s' start_page=%d < chapter start=%d — marking as unknown",
                        sec.get("title", "?"), sp, ch_start_val,
                    )
                    sec["start_page"] = 0
                    sec["end_page"] = 0

    # ── Sanity-check chapter ordering ───────────────────────────────
    # Later chapters must not start before earlier ones.
    if len(chapters) > 1:
        sorted_ch = sorted(chapters, key=lambda c: c.get("order", 0))
        prev_page = 0
        for ch in sorted_ch:
            sp = ch.get("start_page", 0)
            if sp > 0:
                if sp < prev_page:
                    logger.warning(
                        "Chapter '%s' start_page=%d < previous chapter at %d — marking as unknown",
                        ch.get("title", "?"), sp, prev_page,
                    )
                    ch["start_page"] = 0
                    ch["end_page"] = 0
                else:
                    prev_page = sp

    # ── Fill missing chapter page numbers ───────────────────────────
    chapters_with_page = [c for c in chapters if c.get("start_page", 0) > 0]
    chapters_without_page = [c for c in chapters if not c.get("start_page")]

    if chapters_without_page and chapters_with_page:
        # Interpolate: use known chapters as anchors
        all_chapters = chapters  # already in order
        for i, ch in enumerate(all_chapters):
            if ch.get("start_page"):
                continue
            # Find bounding known chapters
            prev_ch = None
            next_ch = None
            for j in range(i - 1, -1, -1):
                if all_chapters[j].get("start_page"):
                    prev_ch = all_chapters[j]
                    break
            for j in range(i + 1, len(all_chapters)):
                if all_chapters[j].get("start_page"):
                    next_ch = all_chapters[j]
                    break
            if prev_ch and next_ch:
                gap = next_ch["start_page"] - prev_ch["start_page"]
                missing_between = sum(
                    1 for c in all_chapters[
                        all_chapters.index(prev_ch) + 1 : all_chapters.index(next_ch)
                    ]
                    if not c.get("start_page")
                )
                offset = all_chapters.index(ch) - all_chapters.index(prev_ch)
                ch["start_page"] = prev_ch["start_page"] + max(
                    1, (gap // max(1, missing_between + 1)) * offset
                )
            elif prev_ch:
                ch["start_page"] = prev_ch.get("end_page", prev_ch["start_page"]) + 1
            elif next_ch:
                ch["start_page"] = max(1, next_ch["start_page"] - 10)

    if chapters_without_page and not chapters_with_page:
        # All chapters unknown — equal distribution
        share = max(1, page_count // len(chapters))
        current = 1
        for ch in chapters:
            ch["start_page"] = current
            ch["end_page"] = min(current + share - 1, page_count)
            current = ch["end_page"] + 1
        if chapters:
            chapters[-1]["end_page"] = page_count

    # Recalculate chapter end_pages — share boundary pages with next chapter
    for i, ch in enumerate(chapters):
        if i + 1 < len(chapters):
            ch["end_page"] = chapters[i + 1].get("start_page", ch.get("start_page", 1) + 10)
        else:
            ch["end_page"] = max(ch.get("start_page", 1), page_count)

    # ── Fill missing section page numbers within each chapter ────────
    for ch in chapters:
        ch_start = max(1, ch.get("start_page", 1))
        ch_end = max(ch_start, ch.get("end_page", page_count))
        sections = ch.get("sections", [])
        if not sections:
            continue

        # Separate known and unknown sections
        sections_with_page = [s for s in sections if s.get("start_page", 0) > 0]
        sections_without_page = [s for s in sections if not s.get("start_page")]

        if sections_without_page:
            if sections_with_page:
                # Interpolate between known sections
                sorted_secs = sorted(sections, key=lambda s: s.get("order", 0))
                for i, sec in enumerate(sorted_secs):
                    if sec.get("start_page"):
                        continue
                    prev_known = next(
                        (sorted_secs[j] for j in range(i - 1, -1, -1)
                         if sorted_secs[j].get("start_page")), None)
                    next_known = next(
                        (sorted_secs[j] for j in range(i + 1, len(sorted_secs))
                         if sorted_secs[j].get("start_page")), None)

                    if prev_known and next_known:
                        gap = next_known["start_page"] - prev_known["start_page"]
                        missing_between = sum(
                            1 for s in sorted_secs[
                                sorted_secs.index(prev_known) + 1 : sorted_secs.index(next_known)
                            ]
                            if not s.get("start_page")
                        )
                        pos = i - sorted_secs.index(prev_known)
                        sec["start_page"] = prev_known["start_page"] + max(
                            1, (gap // max(1, missing_between + 1)) * pos
                        )
                    elif prev_known:
                        sec["start_page"] = prev_known["start_page"] + 1
                    elif next_known:
                        sec["start_page"] = max(ch_start, next_known["start_page"] - 1)
                    else:
                        sec["start_page"] = ch_start + sec.get("order", 0) * 5
            else:
                # All sections unknown — equal distribution within chapter
                share = max(1, (ch_end - ch_start + 1) // len(sections))
                for i, sec in enumerate(sections):
                    sec["start_page"] = ch_start + i * share

        # Clamp section pages to chapter bounds
        for sec in sections:
            sp = sec.get("start_page", ch_start)
            sec["start_page"] = max(ch_start, min(sp, ch_end))

        # Recalculate section end pages — share boundary pages
        sorted_secs = sorted(sections, key=lambda s: s.get("order", 0))
        for i, sec in enumerate(sorted_secs):
            if i + 1 < len(sorted_secs):
                sec["end_page"] = sorted_secs[i + 1].get("start_page", sec.get("start_page", 1) + 5)
            else:
                sec["end_page"] = max(sec.get("start_page", 1), ch_end)

        # Sync chapter bounds from sections
        if sorted_secs:
            ch["start_page"] = sorted_secs[0].get("start_page", ch_start)
            ch["end_page"] = sorted_secs[-1].get("end_page", ch_end)

    # ── Refine section pages using full page text (localized search) ──
    # Only refines sections within their chapter's known page range,
    # avoiding the false matches that plagued the old global title search.
    _refine_section_pages(chapters, page_texts)

    # Recalculate section end pages after refinement — share boundary pages
    for ch in chapters:
        sections = ch.get("sections", [])
        sorted_secs = sorted(sections, key=lambda s: s.get("order", 0))
        for i, sec in enumerate(sorted_secs):
            if i + 1 < len(sorted_secs):
                sec["end_page"] = sorted_secs[i + 1].get("start_page", sec.get("start_page", 1) + 5)
            else:
                sec["end_page"] = max(
                    sec.get("start_page", 1),
                    ch.get("end_page", sec.get("start_page", 1) + 5),
                )
        if sorted_secs:
            ch["start_page"] = sorted_secs[0].get("start_page", ch.get("start_page", 1))
            ch["end_page"] = sorted_secs[-1].get("end_page", ch.get("end_page", 1))

    logger.info(
        "Post-processing complete: %d chapters, native_toc=%s",
        len(chapters), has_native_toc,
    )

    # ── Common: ensure every chapter has at least one section ────────
    for ch in result.get("chapters", []):
        if not ch.get("sections"):
            ch_start = ch.get("start_page", 1)
            ch_end = ch.get("end_page", page_count)
            ch["sections"] = [
                {
                    "title": ch.get("title", ""),
                    "order": 0,
                    "start_page": ch_start,
                    "end_page": ch_end,
                    "estimated_minutes": 45,
                    "knowledge_points": [],
                    "goal": "",
                }
            ]

    # ── Common: assign stable IDs ────────────────────────────────────
    for ch in result.get("chapters", []):
        ch_idx = ch.get("order", 0)
        ch.setdefault("chapter_id", f"ch_{ch_idx:02d}")
        for sec in ch.get("sections", []):
            sec_idx = sec.get("order", 0)
            sec.setdefault("section_id", f"{ch['chapter_id']}_sec_{sec_idx:02d}")

    chapter_count = len(result.get("chapters", []))
    section_count = sum(
        len(ch.get("sections", [])) for ch in result.get("chapters", [])
    )
    logger.info(
        "Textbook structure: %d chapters, %d sections, title=%s, native_toc=%s",
        chapter_count,
        section_count,
        result.get("title", "?"),
        has_native_toc,
    )
    return result
