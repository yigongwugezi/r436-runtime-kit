"""Generate learning-path documents as .docx / .pdf for download.

Architecture::

    generate_learning_path_docx(path_data, day_plan)
        └─ uses python-docx to build a structured Word document

    generate_learning_path_pdf(path_data, day_plan)
        └─ uses fpdf2 to build a structured PDF

Both share the same content-extraction helper ``_build_document_content``
so the rendered structure is identical across formats.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Output directory (mirrors the ppt_generator pattern) ────────────
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "documents"

# ── Import guards ────────────────────────────────────────────────────

try:
    from docx import Document as _Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn

    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False

try:
    from fpdf import FPDF as _FPDF

    _PDF_OK = True
except ImportError:
    _PDF_OK = False

# ── Helpers ──────────────────────────────────────────────────────────

_STATUS_LABEL: dict[str, str] = {
    "mastered": "已完成",
    "completed": "已完成",
    "in_progress": "进行中",
    "available": "未开始",
    "not_started": "未开始",
    "locked": "未解锁",
    "blocked": "受阻",
    "needs_review": "需复习",
}

_DAY_ITEM_LABEL: dict[str, str] = {
    "new": "新课",
    "review": "复习",
    "practice": "练习",
    "diagnosis": "诊断",
    "project": "项目",
}

_ADJUSTMENT_LABEL: dict[str, str] = {
    "accelerated": "已掌握·加速",
    "strengthened": "薄弱·强化",
    "mixed": "部分薄弱",
    "remedial": "前置补救",
    "normal": "",
}


def _status_text(status: str | None) -> str:
    return _STATUS_LABEL.get(status or "", status or "未知")


def _format_minutes(m: int | None) -> str:
    if not m or m <= 0:
        return ""
    if m < 60:
        return f"{m} 分钟"
    h = m // 60
    r = m % 60
    return f"{h}h{r}m" if r else f"{h}h"


def _truncate(text: str, max_len: int = 80) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ══════════════════════════════════════════════════════════════════════
# Shared content extraction
# ══════════════════════════════════════════════════════════════════════


def _build_document_content(
    path_data: dict[str, Any],
    day_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a flat, structured representation of the learning path.

    Both document generators call this so they render identical content.
    """
    stages_raw = path_data.get("stages", []) or []
    course_name = path_data.get("courseName") or path_data.get("course_name", "")
    title = path_data.get("title") or f"{course_name}个性化学习路径"
    description = path_data.get("description", "")
    estimated_days = path_data.get("estimatedDays") or path_data.get("estimated_days", 0)
    overall_progress = path_data.get("overallProgress") or path_data.get("overall_progress", 0) or 0

    # Flatten stats
    total_sections = 0
    total_kps = 0
    total_mastered_kps = 0
    stage_infos: list[dict[str, Any]] = []

    for i, stage in enumerate(stages_raw):
        stage_id = stage.get("id") or stage.get("stage_id", "")
        stage_title = stage.get("title", f"第 {i+1} 阶段")
        stage_desc = stage.get("objective") or stage.get("description", "")
        stage_days = stage.get("estimatedDays") or stage.get("estimated_days", 0)
        stage_order = stage.get("order") or stage.get("ordinal", i + 1)

        chapters_raw = stage.get("chapters", []) or []
        nodes_raw = stage.get("nodes", []) or []

        # Use chapters if available (new format), otherwise nodes (legacy)
        chapters: list[dict[str, Any]] = []
        for ch in chapters_raw:
            ch_id = ch.get("id") or ch.get("chapter_id", "")
            ch_title = ch.get("title", "")
            ch_status = ch.get("status", "")
            sections_raw = ch.get("sections", []) or []

            sections: list[dict[str, Any]] = []
            for sec in sections_raw:
                sec_title = sec.get("title", "")
                sec_goal = sec.get("goal", "")
                sec_minutes = sec.get("estimatedMinutes") or sec.get("estimated_minutes") or 0
                sec_status = sec.get("status", "")
                kps_raw = sec.get("knowledgePoints", []) or sec.get("knowledge_points", [])
                total_sections += 1

                kps: list[dict[str, Any]] = []
                for kp in kps_raw:
                    kp_name = kp.get("name", "")
                    kp_mastery = kp.get("mastery", 0)
                    kp_status = kp.get("status", "")
                    kps.append({"name": kp_name, "mastery": kp_mastery, "status": kp_status})
                    total_kps += 1
                    if kp_status in ("mastered", "completed"):
                        total_mastered_kps += 1

                sections.append({
                    "title": sec_title,
                    "goal": sec_goal,
                    "minutes": sec_minutes,
                    "status": sec_status,
                    "knowledgePoints": kps,
                })

            # Legacy nodes as a special "sections" group when chapters are empty
            chapters.append({
                "id": ch_id,
                "title": ch_title,
                "status": ch_status,
                "sections": sections,
            })

        # If no chapters, create a synthetic chapter from nodes
        if not chapters and nodes_raw:
            node_sections = []
            for n in nodes_raw:
                node_title = n.get("topic", "")
                node_desc = n.get("description", "")
                node_status = n.get("status", "")
                node_mastery = n.get("mastery", 0)
                node_sections.append({
                    "title": node_title,
                    "goal": node_desc,
                    "minutes": 0,
                    "status": node_status,
                    "mastery": node_mastery,
                    "knowledgePoints": [],
                })
                total_kps += 1
                if node_status in ("mastered", "completed"):
                    total_mastered_kps += 1
            if node_sections:
                chapters.append({
                    "id": "",
                    "title": "",
                    "status": "",
                    "sections": node_sections,
                })

        stage_infos.append({
            "id": stage_id,
            "title": stage_title,
            "description": stage_desc,
            "order": stage_order,
            "estimatedDays": stage_days,
            "chapters": chapters,
        })

    # Day plan
    day_blocks: list[dict[str, Any]] = []
    if day_plan:
        raw_days = day_plan.get("days", []) if isinstance(day_plan, dict) else []
        for d in raw_days:
            day_num = d.get("day", 0)
            total_min = d.get("total_minutes", 0)
            raw_items = d.get("items", [])
            items = []
            for item in raw_items:
                item_type = item.get("type", "new")
                items.append({
                    "type": item_type,
                    "type_label": _DAY_ITEM_LABEL.get(item_type, item_type),
                    "title": item.get("title", ""),
                    "minutes": item.get("minutes", 0),
                    "adjustment": item.get("adjustment"),
                    "description": item.get("description", ""),
                })
            day_blocks.append({
                "day": day_num,
                "total_minutes": total_min,
                "items": items,
            })

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M")

    return {
        "title": title,
        "courseName": course_name,
        "description": description,
        "estimatedDays": estimated_days,
        "overallProgress": overall_progress,
        "totalStages": len(stage_infos),
        "totalSections": total_sections,
        "totalKps": total_kps,
        "totalMasteredKps": total_mastered_kps,
        "date": date_str,
        "stages": stage_infos,
        "dayPlan": day_blocks,
    }


# ══════════════════════════════════════════════════════════════════════
# DOCX generation (python-docx)
# ══════════════════════════════════════════════════════════════════════


def generate_learning_path_docx(
    path_data: dict[str, Any],
    day_plan: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> str:
    """Build a .docx from learning-path data and return the file path."""
    if not _DOCX_OK:
        raise RuntimeError("python-docx is not installed. Run: pip install python-docx")

    content = _build_document_content(path_data, day_plan)

    doc = _Document()

    # ── Style defaults ──
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(11)
    style.paragraph_format.space_after = Pt(4)

    # ── Cover page ──
    for _ in range(6):
        doc.add_paragraph("")

    cover_title = doc.add_paragraph()
    cover_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cover_title.add_run(content["courseName"] or "学习路径")
    run.bold = True
    run.font.size = Pt(26)
    run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("个性化学习路径")
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph("")

    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = date_p.add_run(f"生成日期：{content['date']}")
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    doc.add_page_break()

    # ── Overview section ──
    doc.add_heading("一、学习概览", level=1)

    # Quick stats table
    table = doc.add_table(rows=2, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_cell(table, 0, 0, "课程名称", bold=True, bg="E2E8F0")
    _set_cell(table, 1, 0, content["courseName"] or "—", bg="F8FAFC")
    _set_cell(table, 0, 1, "预计天数", bold=True, bg="E2E8F0")
    _set_cell(table, 1, 1, str(content["estimatedDays"]), bg="F8FAFC")
    _set_cell(table, 0, 2, "学习阶段", bold=True, bg="E2E8F0")
    _set_cell(table, 1, 2, str(content["totalStages"]), bg="F8FAFC")
    _set_cell(table, 0, 3, "总体进度", bold=True, bg="E2E8F0")
    _set_cell(table, 1, 3, f"{content['overallProgress']}%", bg="F8FAFC")

    if content["description"]:
        doc.add_paragraph("")
        p = doc.add_paragraph(content["description"])

    doc.add_paragraph("")
    p = doc.add_paragraph(
        f"共 {content['totalKps']} 个知识点，"
        f"已完成 {content['totalMasteredKps']} 个，"
        f"完成率 {round(content['totalMasteredKps'] / max(content['totalKps'], 1) * 100)}%"
    )
    p.runs[0].font.size = Pt(10)

    doc.add_page_break()

    # ── Stages ──
    doc.add_heading("二、各阶段详情", level=1)

    for si, stage in enumerate(content["stages"]):
        doc.add_heading(f"阶段 {stage['order']}：{stage['title']}", level=2)

        if stage["description"]:
            doc.add_paragraph(stage["description"])

        if stage["estimatedDays"]:
            p = doc.add_paragraph()
            run = p.add_run(f"预计 {stage['estimatedDays']} 天")
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

        for ch in stage["chapters"]:
            if not ch["title"] and not ch["sections"]:
                continue

            if ch["title"]:
                doc.add_heading(ch["title"], level=3)

            for sec in ch["sections"]:
                sec_title = sec.get("title", "")
                if not sec_title:
                    continue

                doc.add_heading(sec_title, level=4)

                if sec.get("goal"):
                    p = doc.add_paragraph()
                    run = p.add_run(f"目标：{sec['goal']}")
                    run.font.size = Pt(10)
                    run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

                if sec.get("minutes"):
                    p = doc.add_paragraph()
                    run = p.add_run(f"预计时长：{_format_minutes(sec['minutes'])}")
                    run.font.size = Pt(10)

                if sec["status"]:
                    p = doc.add_paragraph()
                    run = p.add_run(f"状态：{_status_text(sec['status'])}")
                    run.font.size = Pt(10)
                    if sec["status"] in ("mastered", "completed"):
                        run.font.color.rgb = RGBColor(0x16, 0xA3, 0x4A)
                    elif sec["status"] == "in_progress":
                        run.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
                    else:
                        run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

                kps = sec.get("knowledgePoints", [])
                if kps:
                    for kp in kps:
                        kp_text = kp.get("name", "")
                        if kp_text:
                            doc.add_paragraph(kp_text, style="List Bullet")

        doc.add_paragraph("")  # spacing

    # ── Day plan ──
    if content["dayPlan"]:
        doc.add_page_break()
        doc.add_heading("三、日计划", level=1)

        for day_block in content["dayPlan"]:
            day_num = day_block["day"]
            items = day_block.get("items", [])
            total_min = day_block["total_minutes"]

            doc.add_heading(f"第 {day_num} 天（共 {len(items)} 项 · {total_min} 分钟）", level=2)

            for item in items:
                type_label = item.get("type_label", "")
                item_title = item.get("title", "")
                minutes = item.get("minutes", 0)
                adj = item.get("adjustment")

                p = doc.add_paragraph()
                run = p.add_run(f"[{type_label}] ")
                run.bold = True
                run.font.size = Pt(10)
                run.font.color.rgb = _day_type_color(item.get("type", ""))

                run = p.add_run(f"{item_title}")
                run.font.size = Pt(10)

                if minutes:
                    run = p.add_run(f"  ({minutes} 分钟)")
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

                if adj and adj != "normal":
                    adj_label = _ADJUSTMENT_LABEL.get(adj, adj)
                    run = p.add_run(f"  [{adj_label}]")
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0xD9, 0x77, 0x06)

                if item.get("description"):
                    p2 = doc.add_paragraph()
                    run = p2.add_run(item["description"])
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
                    p2.paragraph_format.left_indent = Inches(0.3)

    # ── Summary ──
    doc.add_paragraph("")
    summary_heading = doc.add_paragraph()
    summary_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = summary_heading.add_run("— 文档结束 —")
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"由 EduAgent 于 {content['date']} 自动生成")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)

    # ── Save ──
    if output_path:
        doc.save(output_path)
        return output_path

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = str(OUTPUT_DIR / f"{uuid.uuid4().hex}.docx")
    doc.save(path)
    logger.info("DOCX saved: %s", path)
    return path


# ══════════════════════════════════════════════════════════════════════
# PDF generation (fpdf2)
# ══════════════════════════════════════════════════════════════════════


class _PDFDoc(_FPDF):
    """Custom PDF class with header / footer and optional CJK font."""

    def __init__(self, title_text: str = "") -> None:
        super().__init__()
        self._pdf_title = title_text
        self._cjk_ok = False  # becomes True if a Chinese font was registered
        self.set_auto_page_break(auto=True, margin=20)

    def _register_chinese_font(self) -> bool:
        """Try to register a Chinese TTF font from the system.

        Returns True if a CJK font is available for rendering.
        """
        # Search order: bundled fonts -> Windows system fonts -> macOS/Linux
        candidates = [
            Path(__file__).resolve().parent / "fonts" / "NotoSansSC-Regular.ttf",
            Path(__file__).resolve().parent / "fonts" / "NotoSansSC-Variable.ttf",
            Path("C:/Windows/Fonts/msyh.ttf"),
            Path("C:/Windows/Fonts/simsun.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ]
        for fp in candidates:
            if fp.exists():
                try:
                    # Register regular + bold styles (same file — fpdf2 doesn't
                    # need separate bold fonts; it synthesises weight when needed).
                    self.add_font("CJK", "", str(fp), uni=True)
                    self.add_font("CJK", "B", str(fp), uni=True)
                    self._cjk_ok = True
                    logger.info("Registered Chinese font: %s", fp)
                    return True
                except Exception as exc:
                    logger.debug("Font %s failed: %s", fp, exc)
                    continue

        logger.warning(
            "No Chinese TTF font found. Chinese characters may not render. "
            "Install a CJK font or place one at backend/app/services/fonts/"
        )
        return False

    def _font(self) -> str:
        """Return the active font family name."""
        return "CJK" if self._cjk_ok else "Helvetica"

    def header(self) -> None:
        if self.page_no() <= 1:
            return
        _ft = self._font()
        self.set_font(_ft, "", 8)
        self.set_text_color(0x94, 0xA3, 0xB8)
        self.cell(0, 8, _safe_str(self._pdf_title, 64), align="C")
        self.ln(4)
        self.set_draw_color(0xE2, 0xE8, 0xF0)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        _ft = self._font()
        self.set_font(_ft, "", 8)
        self.set_text_color(0xCB, 0xD5, 0xE1)
        if self._cjk_ok:
            self.cell(0, 10, f"第 {self.page_no()} 页", align="C")
        else:
            self.cell(0, 10, f"Page {self.page_no()}", align="C")


# Color helper for day item types
def _day_type_color(item_type: str) -> RGBColor:
    colors = {
        "new": RGBColor(0x25, 0x63, 0xEB),     # blue
        "review": RGBColor(0x05, 0x9D, 0x69),   # green
        "practice": RGBColor(0xD9, 0x77, 0x06),  # amber
        "diagnosis": RGBColor(0x7C, 0x3A, 0xED), # purple
        "project": RGBColor(0xE1, 0x1D, 0x48),   # rose
    }
    return colors.get(item_type, RGBColor(0x47, 0x54, 0x64))


def _set_cell(table: Any, row: int, col: int, text: str, **kwargs: Any) -> None:
    """Helper to set a table cell value with optional styling."""
    cell = table.cell(row, col)
    cell.text = str(text)
    bold = kwargs.get("bold", False)
    bg = kwargs.get("bg", "")
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in paragraph.runs:
            run.font.size = Pt(10)
            if bold:
                run.bold = True
    if bg:
        shading = cell._element.get_or_add_tcPr()
        shading_elem = shading.makeelement(
            qn("w:shd"),
            {qn("w:fill"): bg, qn("w:val"): "clear"},
        )
        shading.append(shading_elem)


def _safe_str(text: str, max_len: int = 80) -> str:
    """Truncate text safely for display, keeping at most *max_len* chars."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def generate_learning_path_pdf(
    path_data: dict[str, Any],
    day_plan: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> str:
    """Build a .pdf from learning-path data and return the file path."""
    if not _PDF_OK:
        raise RuntimeError("fpdf2 is not installed. Run: pip install fpdf2")

    content = _build_document_content(path_data, day_plan)

    pdf = _PDFDoc(title_text=content["courseName"] or "学习路径")
    pdf._register_chinese_font()
    F = pdf._font  # short alias

    # ── Cover page ──
    pdf.add_page()
    pdf.ln(60)
    pdf.set_font(F(), "B", 28)
    pdf.set_text_color(0x1E, 0x40, 0xAF)
    pdf.cell(0, 15, content["courseName"] or "学习路径", align="C", ln=True)
    pdf.ln(6)
    pdf.set_font(F(), "", 18)
    pdf.set_text_color(0x64, 0x74, 0x8B)
    pdf.cell(0, 12, "个性化学习路径", align="C", ln=True)
    pdf.ln(10)
    pdf.set_font(F(), "", 11)
    pdf.set_text_color(0x94, 0xA3, 0xB8)
    pdf.cell(0, 8, f"生成日期：{content['date']}", align="C", ln=True)
    pdf.ln(4)
    pdf.cell(0, 8, "来源：EduAgent", align="C", ln=True)

    # ── Overview ──
    pdf.add_page()
    pdf.set_font(F(), "B", 18)
    pdf.set_text_color(0x1E, 0x29, 0x3B)
    pdf.cell(0, 12, "一、学习概览", ln=True)
    pdf.ln(4)

    # Stats table
    stats: list[tuple[str, str]] = [
        ("课程名称", content["courseName"] or "—"),
        ("预计天数", str(content["estimatedDays"])),
        ("学习阶段", str(content["totalStages"])),
        ("总体进度", f"{content['overallProgress']}%"),
        ("知识点总数", str(content["totalKps"])),
        ("已完成", f"{content['totalMasteredKps']}"),
    ]
    _pdf_table(pdf, stats, has_cjk=pdf._cjk_ok)

    if content["description"]:
        pdf.ln(4)
        pdf.set_font(F(), "", 10)
        pdf.set_text_color(0x47, 0x54, 0x64)
        pdf.multi_cell(0, 6, content["description"])

    pdf.ln(4)
    pdf.set_font(F(), "", 10)
    pdf.set_text_color(0x94, 0xA3, 0xB8)
    completion_rate = round(content['totalMasteredKps'] / max(content['totalKps'], 1) * 100)
    pdf.cell(0, 6,
        f"共 {content['totalKps']} 个知识点，已完成 {content['totalMasteredKps']} 个，"
        f"完成率 {completion_rate}%",
        ln=True,
    )

    # ── Stages ──
    pdf.add_page()
    pdf.set_font(F(), "B", 18)
    pdf.set_text_color(0x1E, 0x29, 0x3B)
    pdf.cell(0, 12, "二、各阶段详情", ln=True)
    pdf.ln(4)

    for si, stage in enumerate(content["stages"]):
        if si > 0:
            pdf.ln(6)
        pdf.set_font(F(), "B", 14)
        pdf.set_text_color(0x1E, 0x29, 0x3B)
        pdf.cell(0, 10, f"阶段 {stage['order']}：{stage['title']}", ln=True)

        if stage["description"]:
            pdf.set_font(F(), "", 10)
            pdf.set_text_color(0x47, 0x54, 0x64)
            pdf.multi_cell(0, 5.5, stage["description"])

        if stage["estimatedDays"]:
            pdf.set_font(F(), "", 9)
            pdf.set_text_color(0x94, 0xA3, 0xB8)
            pdf.cell(0, 6, f"预计 {stage['estimatedDays']} 天", ln=True)

        for ch in stage["chapters"]:
            if not ch["title"] and not ch["sections"]:
                continue

            if ch["title"]:
                pdf.set_font(F(), "B", 11)
                pdf.set_text_color(0x1E, 0x29, 0x3B)
                pdf.cell(0, 8, ch["title"], ln=True)

            for sec in ch["sections"]:
                sec_title = sec.get("title", "")
                if not sec_title:
                    continue

                pdf.set_font(F(), "B", 10)
                pdf.set_text_color(0x1E, 0x29, 0x3B)
                pdf.cell(0, 7, sec_title, ln=True)

                if sec.get("goal"):
                    pdf.set_font(F(), "", 9)
                    pdf.set_text_color(0x64, 0x74, 0x8B)
                    pdf.cell(0, 5, f"目标：{sec['goal']}", ln=True)

                info_parts = []
                if sec.get("minutes"):
                    info_parts.append(_format_minutes(sec["minutes"]))
                if sec["status"]:
                    info_parts.append(_status_text(sec["status"]))
                if info_parts:
                    pdf.set_font(F(), "", 9)
                    pdf.set_text_color(0x94, 0xA3, 0xB8)
                    pdf.cell(0, 5, " · ".join(info_parts), ln=True)

                kps = sec.get("knowledgePoints", [])
                for kp in kps:
                    kp_name = kp.get("name", "")
                    if kp_name:
                        pdf.set_font(F(), "", 9)
                        pdf.set_text_color(0x47, 0x54, 0x64)
                        pdf.cell(0, 5, f"  • {kp_name}", ln=True)

                pdf.ln(2)

    # ── Day plan ──
    if content["dayPlan"]:
        pdf.add_page()
        pdf.set_font(F(), "B", 18)
        pdf.set_text_color(0x1E, 0x29, 0x3B)
        pdf.cell(0, 12, "三、日计划", ln=True)
        pdf.ln(4)

        for day_block in content["dayPlan"]:
            day_num = day_block["day"]
            items = day_block.get("items", [])
            total_min = day_block["total_minutes"]

            pdf.set_font(F(), "B", 12)
            pdf.set_text_color(0x1E, 0x29, 0x3B)
            pdf.cell(0, 8, f"第 {day_num} 天（共 {len(items)} 项 · {total_min} 分钟）", ln=True)

            for item in items:
                type_label = item.get("type_label", "")
                item_title = item.get("title", "")
                minutes = item.get("minutes", 0)
                adj = item.get("adjustment")

                line = f"  [{type_label}] {item_title}"
                if minutes:
                    line += f"  ({minutes} 分钟)"
                if adj and adj != "normal":
                    adj_label = _ADJUSTMENT_LABEL.get(adj, adj)
                    line += f"  [{adj_label}]"

                pdf.set_font(F(), "", 9)
                pdf.set_text_color(0x1E, 0x29, 0x3B)
                pdf.cell(0, 6, line, ln=True)

                if item.get("description"):
                    pdf.set_font(F(), "", 8)
                    pdf.set_text_color(0x94, 0xA3, 0xB8)
                    pdf.cell(0, 5, f"    {item['description']}", ln=True)

            pdf.ln(3)

        pdf.ln(4)

        # Legend
        pdf.set_font(F(), "B", 10)
        pdf.set_text_color(0x1E, 0x29, 0x3B)
        pdf.cell(0, 7, "图例", ln=True)
        for key, label in _DAY_ITEM_LABEL.items():
            pdf.set_font(F(), "", 9)
            pdf.set_text_color(0x64, 0x74, 0x8B)
            pdf.cell(0, 5, f"  [{label}]", ln=True)

    # ── Footer ──
    pdf.ln(10)
    pdf.set_font(F(), "", 10)
    pdf.set_text_color(0xCB, 0xD5, 0xE1)
    pdf.cell(0, 8, "— 文档结束 —", align="C", ln=True)
    pdf.ln(4)
    pdf.set_font(F(), "", 9)
    pdf.set_text_color(0xCB, 0xD5, 0xE1)
    pdf.cell(0, 6, f"由 EduAgent 于 {content['date']} 自动生成", align="C", ln=True)

    # ── Save ──
    if output_path:
        pdf.output(output_path)
        return output_path

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = str(OUTPUT_DIR / f"{uuid.uuid4().hex}.pdf")
    pdf.output(path)
    logger.info("PDF saved: %s", path)
    return path


def _pdf_table(
    pdf: _PDFDoc,
    rows: list[tuple[str, str]],
    has_cjk: bool = True,
    col_widths: tuple[float, float] = (50, 130),
) -> None:
    """Draw a simple 2-column key-value table on the PDF."""
    _FONT = "CJK" if has_cjk else "Helvetica"
    pdf.set_font(_FONT, "", 10)

    # Header row
    pdf.set_fill_color(0xE2, 0xE8, 0xF0)
    pdf.set_text_color(0x1E, 0x29, 0x3B)
    pdf.cell(col_widths[0], 8, "  项目", border=0, fill=True)
    pdf.cell(col_widths[1], 8, "内容", border=0, fill=True, ln=True)

    pdf.set_fill_color(0xF8, 0xFA, 0xFC)
    pdf.set_text_color(0x47, 0x54, 0x64)
    for i, (key, val) in enumerate(rows):
        fill = i % 2 == 0
        pdf.cell(col_widths[0], 7, f"  {key}", border=0, fill=fill)
        pdf.cell(col_widths[1], 7, val, border=0, fill=fill, ln=True)

def _rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    return (r, g, b)


# ══════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════


def _pdf_table(
    pdf: _PDFDoc,
    rows: list[tuple[str, str]],
    col_widths: tuple[float, float] = (50, 130),
    has_cjk: bool = True,
) -> None:
    """Draw a simple 2-column key-value table."""
    _FONT = "CJK" if has_cjk else "Helvetica"
    pdf.set_font(_FONT, "", 10)

    # Header
    pdf.set_fill_color(0xE2, 0xE8, 0xF0)
    pdf.set_text_color(0x1E, 0x29, 0x3B)
    pdf.cell(col_widths[0], 8, "  项目", border=0, fill=True)
    pdf.cell(col_widths[1], 8, "内容", border=0, fill=True, ln=True)

    pdf.set_fill_color(0xF8, 0xFA, 0xFC)
    pdf.set_text_color(0x47, 0x54, 0x64)
    for i, (key, val) in enumerate(rows):
        fill = i % 2 == 0
        pdf.cell(col_widths[0], 7, "  " + key, border=0, fill=fill)
        pdf.cell(col_widths[1], 7, val, border=0, fill=fill, ln=True)
