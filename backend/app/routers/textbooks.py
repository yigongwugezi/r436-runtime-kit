"""Textbook API router — upload, parse, view PDF textbooks.

Endpoints:
- POST   /api/textbooks/upload        Upload PDF for a subject
- GET    /api/textbooks/{subject_id}  Get textbook metadata
- GET    /api/textbooks/{subject_id}/toc   Get TOC (chapters/sections)
- GET    /api/textbooks/{subject_id}/content  Get extracted text for a section
- POST   /api/textbooks/{subject_id}/parse   Trigger LLM parsing
- DELETE /api/textbooks/{subject_id}  Remove textbook
- GET    /api/textbooks/{subject_id}/pages/{page_num}  Render page as PNG
- GET    /api/textbooks/{subject_id}/pdf       Stream raw PDF
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import settings
from app.db.engine import SessionLocal
from app.db.models import (
    LearnerModel,
    PersonalSubjectModel,
    TextbookModel,
    TextbookPageContentModel,
)
from app.middleware.auth import AuthContext, reject_parent, require_auth
from app.schemas.textbook import (
    TextbookChapterSchema,
    TextbookContentResponse,
    TextbookResponse,
    TextbookSectionSchema,
    TextbookTOCResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["textbooks"])

# ── MIME validation ────────────────────────────────────────────────────────

ALLOWED_MIME_TYPES = {"application/pdf"}
MAX_UPLOAD_SIZE = settings.textbook_max_upload_size


# ── Helpers ───────────────────────────────────────────────────────────────


def _textbook_to_response(tb: TextbookModel) -> TextbookResponse:
    """Serialize a TextbookModel to the public response schema."""
    chapters = None
    if tb.chapters_json and isinstance(tb.chapters_json, list):
        chapters = [
            TextbookChapterSchema(
                chapter_id=ch.get("chapter_id", ""),
                title=ch.get("title", ""),
                order=ch.get("order", 0),
                start_page=ch.get("start_page", 1),
                end_page=ch.get("end_page", 1),
                sections=[
                    TextbookSectionSchema(
                        section_id=sec.get("section_id", ""),
                        title=sec.get("title", ""),
                        order=sec.get("order", 0),
                        start_page=sec.get("start_page", 1),
                        end_page=sec.get("end_page", 1),
                        estimated_minutes=sec.get("estimated_minutes", 45),
                        knowledge_points=sec.get("knowledge_points", []),
                    )
                    for sec in ch.get("sections", [])
                ],
            )
            for ch in tb.chapters_json
        ]

    return TextbookResponse(
        id=tb.id,
        subject_id=tb.subject_id,
        title=tb.title,
        author=tb.author,
        filename=tb.filename,
        file_size_bytes=tb.file_size_bytes,
        page_count=tb.page_count,
        status=tb.status,
        parse_error=tb.parse_error,
        chapters_json=chapters,
        created_at=int(tb.created_at.timestamp() * 1000) if tb.created_at else 0,
        updated_at=int(tb.updated_at.timestamp() * 1000) if tb.updated_at else 0,
    )


def _resolve_textbook_path(textbook_id: str) -> str:
    """Get the absolute path to a textbook PDF file."""
    from app.services.textbook_processor import ensure_textbook_dir

    textbook_dir = ensure_textbook_dir(textbook_id)
    pdf_path = textbook_dir / f"{textbook_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF文件不存在")
    return str(pdf_path)


async def _process_textbook_async(textbook_id: str) -> None:
    """Background task: extract PDF content and run LLM chapter recognition."""
    from app.services.textbook_parser import extract_textbook_structure
    from app.services.textbook_processor import (
        extract_pdf_content,
        extract_toc_from_pdf,
        get_pdf_page_count,
    )

    db = SessionLocal()
    try:
        tb = db.get(TextbookModel, textbook_id)
        if tb is None:
            logger.error("Textbook %s not found for async processing", textbook_id)
            return

        pdf_path = tb.file_path
        if not pdf_path or not __import__("os").path.exists(pdf_path):
            tb.status = "error"
            tb.parse_error = "PDF文件丢失"
            db.commit()
            return

        # Update status
        tb.status = "processing"
        db.commit()

        # Step 1: Get page count
        page_count = get_pdf_page_count(pdf_path)
        tb.page_count = page_count

        # Step 2: Extract per-page markdown via pymupdf4llm
        page_texts = extract_pdf_content(pdf_path)
        logger.info(
            "Extracted %d pages of text from textbook %s", len(page_texts), textbook_id
        )

        # Step 3: Save per-page content
        db.query(TextbookPageContentModel).filter(
            TextbookPageContentModel.textbook_id == textbook_id
        ).delete()

        for pt in page_texts:
            db.add(TextbookPageContentModel(
                textbook_id=textbook_id,
                page_number=pt.get("page_number", 0),
                content=pt.get("content", ""),
                page_label=pt.get("page_label", ""),
            ))
        db.flush()

        # Step 4: Try native PDF TOC
        native_toc = extract_toc_from_pdf(pdf_path)

        # Step 5: LLM chapter recognition
        structure = extract_textbook_structure(page_texts, native_toc)

        if structure.get("title"):
            tb.title = structure["title"]
        if structure.get("author"):
            tb.author = structure["author"]

        # Step 6: Assign IDs and serialize
        chapters = structure.get("chapters", [])
        tb.chapters_json = chapters
        tb.status = "ready"
        db.commit()

        chapter_count = len(chapters)
        section_count = sum(len(ch.get("sections", [])) for ch in chapters)
        logger.info(
            "Textbook %s processed: %d chapters, %d sections, status=ready",
            textbook_id, chapter_count, section_count,
        )

    except Exception as exc:
        logger.exception("Async processing failed for textbook %s", textbook_id)
        try:
            tb = db.get(TextbookModel, textbook_id)
            if tb:
                tb.status = "error"
                tb.parse_error = str(exc)[:1000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Upload PDF
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/textbooks/upload")
async def upload_textbook(
    background_tasks: BackgroundTasks,
    subject_id: str = Form(...),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(reject_parent),
) -> dict:
    """Upload a PDF textbook for a personal subject.

    The textbook is saved to disk and async processing is triggered.
    The client should poll GET /api/textbooks/{subject_id} to check status.
    """
    # Validate subject ownership
    db = SessionLocal()
    try:
        ps = db.get(PersonalSubjectModel, subject_id)
        if ps is None:
            raise HTTPException(status_code=404, detail="科目不存在")
        if ps.learner_id != auth.learner_id:
            raise HTTPException(status_code=403, detail="无权为此科目上传教材")

        # Validate file MIME type
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file.content_type}，仅支持 PDF",
            )

        # Read file
        file_bytes = await file.read()
        if len(file_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件过大（最大 {MAX_UPLOAD_SIZE // (1024*1024)} MB）",
            )

        # Check if textbook already exists for this subject
        existing = db.query(TextbookModel).filter(
            TextbookModel.subject_id == subject_id
        ).first()
        if existing:
            # Delete old textbook files and records
            from app.services.textbook_processor import delete_textbook_files

            db.query(TextbookPageContentModel).filter(
                TextbookPageContentModel.textbook_id == existing.id
            ).delete()
            db.delete(existing)
            db.flush()
            delete_textbook_files(existing.id)

        # Create textbook record
        textbook_id = f"tb_{uuid.uuid4().hex[:12]}"
        from app.services.textbook_processor import save_uploaded_pdf

        file_path = save_uploaded_pdf(textbook_id, file_bytes, file.filename or "textbook.pdf")

        tb = TextbookModel(
            id=textbook_id,
            subject_id=subject_id,
            learner_id=auth.learner_id,
            filename=file.filename or "textbook.pdf",
            file_path=file_path,
            file_size_bytes=len(file_bytes),
            mime_type=file.content_type or "application/pdf",
            status="uploading",
        )
        db.add(tb)

        # Link textbook to subject
        ps.textbook_id = textbook_id

        db.commit()
        db.refresh(tb)

        # Trigger async processing
        background_tasks.add_task(_process_textbook_async, textbook_id)

        return {
            "status": "success",
            "data": {"textbook": _textbook_to_response(tb).model_dump()},
            "message": "教材上传成功，正在后台处理",
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Get textbook metadata
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/textbooks/{subject_id}")
def get_textbook(
    subject_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get textbook metadata for a subject."""
    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            return {
                "status": "success",
                "data": {"textbook": None},
                "message": "该科目没有教材",
            }

        return {
            "status": "success",
            "data": {"textbook": _textbook_to_response(tb).model_dump()},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Get TOC (Table of Contents)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/textbooks/{subject_id}/toc")
def get_textbook_toc(
    subject_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get the textbook's table of contents (chapters and sections)."""
    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            return {
                "status": "success",
                "data": {"toc": None},
                "message": "该科目没有教材",
            }

        toc = TextbookTOCResponse(
            textbook=_textbook_to_response(tb),
            chapters=_textbook_to_response(tb).chapters_json or [],
        )

        return {
            "status": "success",
            "data": {"toc": toc.model_dump()},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Get extracted content for a section
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/textbooks/{subject_id}/content")
def get_textbook_content(
    subject_id: str,
    section_id: str = Query(default=""),
    page_start: int = Query(default=0),
    page_end: int = Query(default=0),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Get extracted markdown text for a textbook section or page range.

    Used by quiz generation and smart tutor as the "lecture notes" equivalent.

    Query params:
        section_id: Find pages from the section in chapters_json.
        page_start / page_end: Explicit page range (takes precedence).
    """
    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            return {
                "status": "success",
                "data": {"content": None},
                "message": "该科目没有教材",
            }

        # Determine page range
        if page_start > 0 and page_end > 0:
            start, end = page_start, page_end
        elif section_id:
            # Look up section in chapters_json
            start, end = 0, 0
            for ch in (tb.chapters_json or []):
                for sec in ch.get("sections", []):
                    if sec.get("section_id") == section_id:
                        start = sec.get("start_page", 0)
                        end = sec.get("end_page", 0)
                        break
                if start > 0:
                    break

            if start == 0:
                return {
                    "status": "success",
                    "data": {"content": None},
                    "message": "未找到该小节的教材内容",
                }
        else:
            return {
                "status": "error",
                "data": None,
                "message": "请指定 section_id 或 page_start/page_end",
            }

        # Query page contents
        pages = (
            db.query(TextbookPageContentModel)
            .filter(
                TextbookPageContentModel.textbook_id == tb.id,
                TextbookPageContentModel.page_number >= start,
                TextbookPageContentModel.page_number <= end,
            )
            .order_by(TextbookPageContentModel.page_number)
            .all()
        )

        content = "\n\n".join(
            p.content for p in pages if p.content
        )

        result = TextbookContentResponse(
            textbook_id=tb.id,
            section_id=section_id or None,
            page_start=start,
            page_end=end,
            content=content,
        )

        return {
            "status": "success",
            "data": {"content": result.model_dump()},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Trigger LLM parsing
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/textbooks/{subject_id}/parse")
async def parse_textbook(
    subject_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(reject_parent),
) -> dict:
    """Re-trigger LLM chapter recognition for an existing textbook."""
    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            raise HTTPException(status_code=404, detail="教材不存在")

        # Verify ownership
        if tb.learner_id != auth.learner_id:
            raise HTTPException(status_code=403, detail="无权操作此教材")

        if tb.status == "processing":
            return {
                "status": "success",
                "data": {"textbook": _textbook_to_response(tb).model_dump()},
                "message": "教材正在处理中",
            }

        tb.status = "uploading"
        db.commit()

        background_tasks.add_task(_process_textbook_async, tb.id)

        return {
            "status": "success",
            "data": {"textbook": _textbook_to_response(tb).model_dump()},
            "message": "已触发重新解析",
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Delete textbook
# ═══════════════════════════════════════════════════════════════════════════


@router.delete("/textbooks/{subject_id}")
def delete_textbook(
    subject_id: str,
    auth: AuthContext = Depends(reject_parent),
) -> dict:
    """Remove a textbook and all its data."""
    from app.services.textbook_processor import delete_textbook_files

    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            raise HTTPException(status_code=404, detail="教材不存在")

        if tb.learner_id != auth.learner_id:
            raise HTTPException(status_code=403, detail="无权删除此教材")

        textbook_id = tb.id

        # Clear reference from subject
        ps = db.get(PersonalSubjectModel, subject_id)
        if ps:
            ps.textbook_id = None

        # Delete page contents
        db.query(TextbookPageContentModel).filter(
            TextbookPageContentModel.textbook_id == textbook_id
        ).delete()

        # Delete textbook record
        db.delete(tb)
        db.commit()

        # Delete files from disk
        delete_textbook_files(textbook_id)

        return {
            "status": "success",
            "data": {},
            "message": "教材已删除",
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Serve PDF page as PNG image
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/textbooks/{subject_id}/pages/{page_num}")
def get_textbook_page_image(
    subject_id: str,
    page_num: int,
    zoom: float = Query(default=1.5, ge=0.5, le=4.0),
    auth: AuthContext = Depends(require_auth),
):
    """Render a single PDF page as a PNG image.

    Used by the frontend PDF viewer component.
    """
    from app.services.textbook_processor import render_page_image

    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            raise HTTPException(status_code=404, detail="教材不存在")

        pdf_path = tb.file_path
    finally:
        db.close()

    if not pdf_path or not __import__("os").path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF文件不存在")

    try:
        img_bytes = render_page_image(pdf_path, page_num, zoom)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(content=img_bytes, media_type="image/png")


# ═══════════════════════════════════════════════════════════════════════════
# 8. Serve raw PDF file
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/textbooks/{subject_id}/pdf")
def get_textbook_pdf(
    subject_id: str,
    auth: AuthContext = Depends(require_auth),
):
    """Serve the full PDF file for inline viewing or download."""
    db = SessionLocal()
    try:
        tb = (
            db.query(TextbookModel)
            .filter(TextbookModel.subject_id == subject_id)
            .first()
        )
        if tb is None:
            raise HTTPException(status_code=404, detail="教材不存在")

        pdf_path = tb.file_path
        filename = tb.filename or "textbook.pdf"
    finally:
        db.close()

    if not pdf_path or not __import__("os").path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF文件不存在")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": "inline"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. List all textbooks (for resource library)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/textbooks")
def list_textbooks(
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """List all textbooks for the current learner.

    Used by the resource library to show imported textbooks.
    """
    db = SessionLocal()
    try:
        textbooks = (
            db.query(TextbookModel)
            .filter(TextbookModel.learner_id == auth.learner_id)
            .order_by(TextbookModel.created_at.desc())
            .all()
        )

        results = [_textbook_to_response(tb).model_dump() for tb in textbooks]

        return {
            "status": "success",
            "data": {"textbooks": results},
        }
    finally:
        db.close()
