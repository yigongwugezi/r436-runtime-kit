"""Generate professional .pptx presentations from LLM-structured slide content.

Design principles (adapted from DeepTutor pptx skill):
  - Use layout placeholders instead of raw textboxes where possible
  - paragraph.level for bullets instead of manual • glyphs
  - Topic-appropriate palette (not default blue)
  - Dark title/closing slides, light content slides
  - Varied layouts across slides (title, content, quote, two-column, summary)
  - Type scale: title 40pt, section-headers 22pt, body 16pt, footnotes 12pt
  - Minimum 0.5 in margins; word_wrap=True everywhere
  - Reopen with python-pptx after saving to verify slide count / key text
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "ppt"

# ── Education-oriented colour palette ──
# Dark indigo for covers & closing slides; warm-white for content
DARK_BG   = (0x1E, 0x1B, 0x4B)   # deep indigo
LIGHT_BG  = (0xFA, 0xFA, 0xF5)   # warm white
AMBER     = (0xD9, 0x77, 0x06)   # title accent
EMERALD   = (0x05, 0x96, 0x69)   # key-concept highlight
SLATE     = (0x1E, 0x29, 0x3B)   # body text on light bg
STONE     = (0x64, 0x74, 0x8B)   # secondary text
DARK_TEXT  = (0x0F, 0x17, 0x2A)  # headings on light bg
WHITE_SOFT = (0xF1, 0xF5, 0xF9)  # text on dark bg


def _rgb(r: int, g: int, b: int):
    from pptx.dml.color import RGBColor
    return RGBColor(r, g, b)


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def generate_pptx(topic: str, difficulty: str = "medium", session_id: str = "") -> str | None:
    """Generate a polished .pptx presentation for *topic* and return the file path.

    Two-stage LLM pipeline:
      1. DeepSeek (planner)  →  detailed teaching outline
      2. Doubao (ppt_writer) →  rich slide content from the outline

    Returns None when the pipeline fails at any stage.
    """
    # ── Stage 1: DeepSeek generates teaching outline ──
    outline = _generate_outline(topic, difficulty)
    if not outline:
        logger.warning("PPT: outline generation failed")
        return None

    # ── Stage 2: Doubao generates rich slide content ──
    slides_raw = _generate_slide_content(topic, difficulty, outline)
    if not slides_raw:
        logger.warning("PPT: slide content generation failed")
        return None

    # ── Stage 3: parse into structured slide data ──
    slides_parsed = _parse_slides(slides_raw)
    if not slides_parsed or len(slides_parsed) < 2:
        logger.warning("PPT: only %d slides parsed — need >= 2", len(slides_parsed or []))
        return None

    # ── Stage 4: build .pptx ──
    try:
        filepath = _build_pptx(slides_parsed, topic)
    except ImportError:
        logger.warning("PPT: python-pptx not installed")
        return None
    except Exception as exc:
        logger.warning("PPT: build failed: %s", exc)
        return None

    # ── Stage 5: verify output ──
    try:
        from pptx import Presentation
        prs = Presentation(filepath)
        assert len(prs.slides) >= 2, "too few slides"
        logger.info("PPT verified: %s (%d slides)", filepath, len(prs.slides))
    except Exception as exc:
        logger.warning("PPT: verification failed: %s", exc)
        return None

    return filepath


# ──────────────────────────────────────────────────────────────────────
# Stage 1: DeepSeek produces teaching outline
# ──────────────────────────────────────────────────────────────────────

def _generate_outline(topic: str, difficulty: str) -> str | None:
    """Use DeepSeek to design a detailed teaching outline."""
    try:
        from app.services.llm_factory import get_planner
        llm_fn = get_planner()
    except Exception as exc:
        logger.warning("PPT: DeepSeek unavailable: %s", exc)
        return None

    diff_guide = {
        "easy":   "面向零基础入门学习者",
        "medium": "面向有一定了解的学习者，兼顾基础与深度",
        "hard":   "面向进阶学习者，包含技术细节和高级概念",
    }.get(difficulty, "面向有一定了解的学习者")

    prompt = f"""你是资深课程设计师。为「{topic}」设计一份教学大纲。{diff_guide}。

输出结构（不要 Markdown，纯文本）：
1. 课程定位（一句话）
2. 核心知识点（5-8个，按学习顺序排列）
3. 每个知识点的讲授要点（每个2-3句，包含关键概念、常见误区、有趣例子）
4. 适合的对比/分类角度（用于两栏对比页）
5. 一句名人名言或核心洞见（与主题相关）
6. 2-3个思考题（检验学习效果）
7. 总结建议

输出要具体、有料、有教学感染力。"""

    try:
        completion, usage = llm_fn(prompt, max_tokens=4000, temperature=0.4)
        if completion is None:
            return None
        content = completion.choices[0].message.content
        logger.info("PPT outline generated (%d prompt / %d completion tokens)",
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return str(content)
    except Exception as exc:
        logger.warning("PPT: outline LLM failed: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────
# Stage 2: Doubao writes slide content from the outline
# ──────────────────────────────────────────────────────────────────────

def _generate_slide_content(topic: str, difficulty: str, outline: str) -> str | None:
    """Use Doubao (ark) to produce rich, engaging slide content."""
    try:
        from app.services.llm_factory import get_ppt_writer
        llm_fn = get_ppt_writer()
    except Exception as exc:
        logger.warning("PPT: Doubao unavailable: %s", exc)
        return None

    diff_label = {"easy": "入门", "medium": "进阶", "hard": "高级"}.get(difficulty, "进阶")

    prompt = f"""你是一位深受学生喜爱的金牌讲师，正在为「{topic}」制作一份{10+len(outline)%3}页的PPT。

以下是教学大纲：
---
{outline[:3000]}
---

请按照以下格式输出幻灯片内容，每页用 --- 分隔：

[layout] cover | content | two_column | quote | summary
[title] 本页标题（精炼有力，吸引注意力）
[points]
- 核心要点（用生动语言，结合大纲中的例子和误区）
  - 补充说明或例子（可选）
[/points]
[keyword] 核心关键词（用 / 分隔）
[notes] 讲师备注（给讲师的一个授课小提示）

幻灯片结构：
1. [cover]      封面 — 课程标题 + 一句吸引人的副标题
2. [content]    为什么学这个 — 趣味引入，激发好奇
3. [content]    核心概念全景 — 知识地图
4-5. [content]  分点深度讲解 — 逻辑递进
6. [two_column] 对比/辨析 — 用大纲中的对比角度
7. [quote]      金句启发 — 用大纲中的名言
8. [content]    实战案例 — 让知识落地
9. [summary]    总结回顾 + 学习建议
10. [content]   思考题 — 检验学习效果

风格要求：
- 语言生动有感染力，像在对话而非念稿
- 善用比喻和场景化表达
- 避免枯燥的教科书语气
- 要点精炼，每页不超过4条一级要点

只输出格式化内容，不要额外说明。"""

    try:
        completion, usage = llm_fn(prompt, max_tokens=8000, temperature=0.6)
        if completion is None:
            return None
        content = completion.choices[0].message.content
        logger.info("PPT slides generated (%d prompt / %d completion tokens)",
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return str(content)
    except Exception as exc:
        logger.warning("PPT: slide content LLM failed: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────
# Slide parsing
# ──────────────────────────────────────────────────────────────────────

def _parse_slides(raw: str) -> list[dict[str, Any]]:
    """Parse LLM output into a list of slide dicts.

    Each slide dict: {layout, title, points, keyword, notes}
    points is a list of {text, level} dicts where level 0 = primary, 1 = secondary.
    """
    blocks = [b.strip() for b in raw.split("---") if b.strip()]
    slides: list[dict[str, Any]] = []

    for block in blocks:
        slide: dict[str, Any] = {
            "layout": "content",
            "title": "",
            "points": [],
            "keyword": "",
            "notes": "",
        }

        # ── Parse tagged fields ──
        lines = block.split("\n")
        in_points = False
        pending_points: list[dict[str, Any]] = []

        for line in lines:
            stripped = line.strip()

            # Layout tag
            m = re.match(r"^\[layout\]\s*(.+)", stripped, re.IGNORECASE)
            if m:
                slide["layout"] = m.group(1).strip().lower()
                continue

            # Title tag
            m = re.match(r"^\[title\]\s*(.+)", stripped, re.IGNORECASE)
            if m:
                slide["title"] = m.group(1).strip()
                continue

            # Points block start
            if re.match(r"^\[points\]", stripped, re.IGNORECASE):
                in_points = True
                continue
            # Points block end
            if re.match(r"^\[/points\]", stripped, re.IGNORECASE):
                in_points = False
                continue

            # Keyword tag
            m = re.match(r"^\[keyword\]\s*(.+)", stripped, re.IGNORECASE)
            if m:
                slide["keyword"] = m.group(1).strip()
                continue

            # Notes tag
            m = re.match(r"^\[notes\]\s*(.+)", stripped, re.IGNORECASE)
            if m:
                slide["notes"] = m.group(1).strip()
                continue

            # Inside points block
            if in_points:
                # Secondary bullet (indented, starts with - or spaces then -)
                m2 = re.match(r"^(?:\s{2,}|\t)[-–—]\s*(.+)", stripped)
                if m2:
                    pending_points.append({"text": m2.group(1).strip(), "level": 1})
                    continue
                # Primary bullet
                m1 = re.match(r"^[-–—*]\s*(.+)", stripped)
                if m1:
                    pending_points.append({"text": m1.group(1).strip(), "level": 0})
                    continue

        # ── Fallback: if no tagged points found, extract any bullet-like lines ──
        if not pending_points:
            for line in lines:
                stripped = line.strip()
                if re.match(r"^[-–—*]\s*(.+)", stripped):
                    pending_points.append({
                        "text": re.sub(r"^[-–—*]\s*", "", stripped).strip(),
                        "level": 0,
                    })

        slide["points"] = pending_points

        # ── Fallback title ──
        if not slide["title"]:
            # Use first non-tag, non-bullet line as title
            for line in lines:
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("[")
                    and not re.match(r"^[-–—*]", stripped)
                ):
                    slide["title"] = stripped.lstrip("#").strip()
                    break

        slides.append(slide)

    return slides


# ──────────────────────────────────────────────────────────────────────
# .pptx construction (python-pptx)
# ──────────────────────────────────────────────────────────────────────

def _build_pptx(slides: list[dict[str, Any]], topic: str) -> str:
    """Build a polished .pptx file from parsed slide data."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.oxml.ns import qn

    prs = Presentation()
    prs.slide_width  = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # ── Inspect available layouts ──
    layouts = _inspect_layouts(prs)

    # Helper: pick the best layout for a slide type
    def _pick_layout(ltype: str):
        # Prefer Title Slide (cover), Title and Content (content), Title Only (quote/two_column)
        if ltype in ("cover", "summary"):
            return prs.slide_layouts[0]  # Title Slide
        if ltype in ("quote",):
            return prs.slide_layouts[layouts.get("blank", 6)]
        if ltype in ("two_column",):
            return prs.slide_layouts[layouts.get("blank", 6)]
        return prs.slide_layouts[layouts.get("title_content", 1)]

    total = len(slides)
    for i, sd in enumerate(slides):
        ltype = sd.get("layout", "content")
        layout = _pick_layout(ltype)
        slide = prs.slides.add_slide(layout)

        # ── Background ──
        is_dark = ltype in ("cover", "quote", "summary")
        bg_rgb = DARK_BG if is_dark else LIGHT_BG
        _set_solid_bg(slide, bg_rgb)

        # ── Title ──
        title_text = sd.get("title", "")
        if title_text and slide.shapes.title:
            _set_title(slide.shapes.title, title_text, ltype)
        elif title_text:
            # No title placeholder → add a textbox
            _add_title_textbox(slide, title_text, ltype)

        # ── Body points ──
        points = sd.get("points", [])
        if points:
            if ltype == "two_column":
                _add_two_column_points(slide, points, is_dark)
            elif ltype == "quote":
                _add_quote_body(slide, points, is_dark)
            else:
                _add_content_points(slide, points, is_dark, ltype)

        # ── Keyword badge (content slides) ──
        keyword = sd.get("keyword", "")
        if keyword and ltype not in ("cover", "quote"):
            _add_keyword_badge(slide, keyword, is_dark)

        # ── Slide number (except cover) ──
        if i > 0:
            _add_slide_number(slide, i, total, is_dark)

        # ── Notes ──
        notes_text = sd.get("notes", "")
        if notes_text:
            _add_speaker_notes(slide, notes_text)

    # ── Save ──
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.pptx"
    filepath = OUTPUT_DIR / filename
    prs.save(str(filepath))
    logger.info("PPT generated: %s (%d slides)", filepath, total)
    return str(filepath)


# ──────────────────────────────────────────────────────────────────────
# Layout inspection
# ──────────────────────────────────────────────────────────────────────

def _inspect_layouts(prs) -> dict[str, int]:
    """Map friendly names to layout indices for the default template."""
    mapping: dict[str, int] = {}
    for idx, lay in enumerate(prs.slide_layouts):
        name = (lay.name or "").lower()
        if "title slide" in name or "title" == name:
            mapping.setdefault("title", idx)
        if "title and content" in name or "title, content" in name:
            mapping.setdefault("title_content", idx)
        if "title only" in name:
            mapping.setdefault("title_only", idx)
        if "blank" in name:
            mapping.setdefault("blank", idx)
    # Defaults for common template variants
    mapping.setdefault("title", 0)
    mapping.setdefault("title_content", 1)
    mapping.setdefault("blank", 6)
    return mapping


# ──────────────────────────────────────────────────────────────────────
# Slide element helpers
# ──────────────────────────────────────────────────────────────────────

def _set_solid_bg(slide, rgb: tuple[int, int, int]) -> None:
    from pptx.dml.color import RGBColor
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(*rgb)


def _set_title(title_shape, text: str, ltype: str) -> None:
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    title_shape.text = ""
    tf = title_shape.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text

    if ltype in ("cover",):
        p.font.size = Pt(44)
        p.font.bold = True
        p.font.color.rgb = _rgb(*AMBER)
        p.alignment = PP_ALIGN.CENTER
    elif ltype in ("summary",):
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = _rgb(*AMBER)
        p.alignment = PP_ALIGN.CENTER
    elif ltype in ("quote",):
        p.font.size = Pt(32)
        p.font.bold = False
        p.font.italic = True
        p.font.color.rgb = _rgb(*WHITE_SOFT)
        p.alignment = PP_ALIGN.CENTER
    else:
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.color.rgb = _rgb(*DARK_TEXT)


def _add_title_textbox(slide, text: str, ltype: str) -> None:
    """Fallback: add a title as a manual textbox when no placeholder exists."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    left = Inches(0.8)
    top = Inches(0.6)
    width = Inches(11.7)
    height = Inches(1.2)

    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = _rgb(*DARK_TEXT)
    p.alignment = PP_ALIGN.LEFT


def _add_content_points(slide, points: list[dict], is_dark: bool, ltype: str) -> None:
    """Add bullet points using the content placeholder (or a textbox fallback).

    Uses paragraph.level for indentation instead of manual bullets.
    """
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    text_color = _rgb(*WHITE_SOFT) if is_dark else _rgb(*SLATE)
    heading_color = _rgb(*AMBER) if is_dark else _rgb(*DARK_TEXT)

    # Try to use the content placeholder (placeholder idx 1 on Title+Content)
    body_shape = None
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == 1:
            body_shape = shape
            break

    if body_shape and body_shape.has_text_frame:
        tf = body_shape.text_frame
        tf.clear()
        tf.word_wrap = True
        _fill_text_frame(tf, points, text_color, heading_color)
    else:
        # Fallback: manual textbox
        left = Inches(1.0)
        top = Inches(2.0) if ltype in ("cover", "summary") else Inches(1.8)
        width = Inches(11.3)
        height = Inches(5.0)

        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True
        _fill_text_frame(tf, points, text_color, heading_color)


def _add_two_column_points(slide, points: list[dict], is_dark: bool) -> None:
    """Split points into two columns side-by-side."""
    from pptx.util import Inches, Pt
    text_color = _rgb(*WHITE_SOFT) if is_dark else _rgb(*SLATE)
    heading_color = _rgb(*AMBER) if is_dark else _rgb(*DARK_TEXT)

    primary = [p for p in points if p.get("level", 0) == 0]
    mid = max(1, len(primary) // 2)
    left_pts = primary[:mid]
    right_pts = primary[mid:]

    col_w = Inches(5.5)
    col_h = Inches(5.0)
    top_y = Inches(2.2)

    for col_idx, col_pts in enumerate([left_pts, right_pts]):
        if not col_pts:
            continue
        left_x = Inches(1.0) if col_idx == 0 else Inches(6.8)
        txBox = slide.shapes.add_textbox(left_x, top_y, col_w, col_h)
        tf = txBox.text_frame
        tf.word_wrap = True
        _fill_text_frame(tf, col_pts, text_color, heading_color)


def _add_quote_body(slide, points: list[dict], is_dark: bool) -> None:
    """Render the quote slide: a large centred quote with attribution."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    quote_text = points[0]["text"] if points else ""
    attribution = points[1]["text"] if len(points) > 1 else ""

    # Quote
    left = Inches(1.5)
    top = Inches(2.5)
    width = Inches(10.3)
    height = Inches(3.0)
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"「{quote_text}」"
    p.font.size = Pt(30)
    p.font.italic = True
    p.font.color.rgb = _rgb(*WHITE_SOFT)
    p.alignment = PP_ALIGN.CENTER

    # Attribution
    if attribution:
        p2 = tf.add_paragraph()
        p2.text = f"— {attribution}"
        p2.font.size = Pt(18)
        p2.font.color.rgb = _rgb(*AMBER)
        p2.alignment = PP_ALIGN.CENTER
        p2.space_before = Pt(16)


def _fill_text_frame(tf, points: list[dict], text_color, heading_color) -> None:
    """Fill a text_frame with hierarchical bullet points using paragraph.level."""
    from pptx.util import Pt

    first = True
    for pt in points:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.text = pt.get("text", "")
        level = pt.get("level", 0)
        p.level = level

        if level == 0:
            p.font.size = Pt(18)
            p.font.bold = True
            p.font.color.rgb = heading_color
        else:
            p.font.size = Pt(15)
            p.font.bold = False
            p.font.color.rgb = text_color

        p.space_after = Pt(6)
        p.space_before = Pt(2)


def _add_keyword_badge(slide, keyword: str, is_dark: bool) -> None:
    """Add a small keyword badge at the bottom-right."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    left = Inches(7.0)
    top = Inches(6.7)
    width = Inches(5.8)
    height = Inches(0.55)

    badge = slide.shapes.add_textbox(left, top, width, height)
    tf = badge.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"🔑 {keyword}"
    p.font.size = Pt(12)
    p.font.color.rgb = _rgb(*EMERALD) if not is_dark else _rgb(*AMBER)
    p.font.italic = True
    p.alignment = PP_ALIGN.RIGHT


def _add_slide_number(slide, idx: int, total: int, is_dark: bool) -> None:
    """Add a discrete slide number at the bottom-right."""
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    left = Inches(12.0)
    top = Inches(7.0)
    width = Inches(1.0)
    height = Inches(0.4)

    nb = slide.shapes.add_textbox(left, top, width, height)
    tf = nb.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.text = f"{idx}/{total}"
    p.font.size = Pt(10)
    p.font.color.rgb = _rgb(*STONE) if not is_dark else _rgb(*STONE)
    p.alignment = PP_ALIGN.RIGHT


def _add_speaker_notes(slide, notes_text: str) -> None:
    """Set speaker notes for the slide."""
    try:
        notes_slide = slide.notes_slide
        tf = notes_slide.notes_text_frame
        tf.clear()
        tf.paragraphs[0].text = notes_text
    except Exception:
        # Some templates don't support notes; silently skip
        pass
