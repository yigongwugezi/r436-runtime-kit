"""Generate real .pptx files from LLM-structured slide content."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "ppt"


def generate_pptx(topic: str, difficulty: str = "medium", session_id: str = "") -> str | None:
    """Generate a .pptx presentation for *topic* and return the file path."""
    try:
        from app.services.llm_client import get_llm_client
        llm = get_llm_client()
    except Exception as e:
        logger.warning("PPT: LLM unavailable: %s", e)
        return None

    # ── Step 1: LLM generates slide content ──
    prompt = f"""为「{topic}」生成一份 PPT 演示文稿的完整内容。难度：{difficulty}。

格式：每页用 --- 分隔。每页包含：
- 标题
- 核心要点（3-5条）
- 图解建议（1句话，建议放什么图）
- 本页小结（1句话）

共 8-10 页，结构：
1. 封面（课程标题）
2-3. 概念引入
4-6. 核心讲解（分点展开）
7-8. 实例/应用
9. 总结回顾
10. 思考题

只输出内容，不要额外说明。"""

    try:
        raw = llm.chat(messages=[
            {"role": "system", "content": "你是课程讲师。输出结构清晰的 PPT 内容。"},
            {"role": "user", "content": prompt},
        ], temperature=0.5, max_tokens=2500)
    except Exception as e:
        logger.warning("PPT: LLM call failed: %s", e)
        return None

    if not raw or len(raw) < 100:
        return None

    slides = [s.strip() for s in raw.split("---") if s.strip()]
    if len(slides) < 3:
        return None

    # ── Step 2: Build .pptx with python-pptx ──
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        BG = RGBColor(0x1A, 0x1A, 0x2E)
        ACCENT = RGBColor(0x3B, 0x82, 0xF6)
        GOLD = RGBColor(0xF5, 0x9E, 0x0B)
        WHITE = RGBColor(0xF1, 0xF5, 0xF9)

        for i, slide_text in enumerate(slides):
            lines = slide_text.strip().split("\n")
            title_line = lines[0].lstrip("#").strip() if lines else f"第{i+1}页"
            body_lines = [l.lstrip("- ").strip() for l in lines[1:] if l.strip().startswith(("-", "*", "1.", "2.", "3."))]

            layout_idx = 0 if i == 0 else 1
            slide_layout = prs.slide_layouts[layout_idx] if layout_idx < len(prs.slide_layouts) else prs.slide_layouts[0]
            slide = prs.slides.add_slide(slide_layout)

            # Background
            bg = slide.background
            fill = bg.fill
            fill.solid()
            fill.fore_color.rgb = BG

            # Title
            if slide.shapes.title:
                title_shape = slide.shapes.title
                title_shape.text = title_line
                for paragraph in title_shape.text_frame.paragraphs:
                    paragraph.font.size = Pt(36)
                    paragraph.font.color.rgb = GOLD if i == 0 else WHITE
                    paragraph.font.bold = True
                    paragraph.alignment = PP_ALIGN.CENTER if i == 0 else PP_ALIGN.LEFT

            # Body
            if body_lines:
                left = Inches(0.8)
                top = Inches(2.0)
                width = Inches(11.7)
                height = Inches(5.0)
                txBox = slide.shapes.add_textbox(left, top, width, height)
                tf = txBox.text_frame
                tf.word_wrap = True
                for j, line in enumerate(body_lines[:8]):
                    if j == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = f"• {line}"
                    p.font.size = Pt(22)
                    p.font.color.rgb = WHITE
                    p.space_after = Pt(12)

        # ── Save ──
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.pptx"
        filepath = OUTPUT_DIR / filename
        prs.save(str(filepath))
        logger.info("PPT generated: %s (%d slides)", filepath, len(slides))
        return str(filepath)

    except ImportError:
        logger.warning("PPT: python-pptx not installed")
        return None
    except Exception as e:
        logger.warning("PPT generation failed: %s", e)
        return None
