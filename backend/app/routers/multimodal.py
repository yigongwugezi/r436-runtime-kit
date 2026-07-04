"""Debug/test endpoint for MultimodalAgent."""

from __future__ import annotations

import base64
import json
import uuid
from email.parser import BytesParser
from email.policy import default
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

# MultimodalAgent removed — OpenMAIC handles multimodal tasks externally
class _MultimodalStub:
    def run(self, context): return {"result": None, "error": "Multimodal service not configured"}
MultimodalAgent = _MultimodalStub
from app.db.engine import SessionLocal
from app.db.repository import upsert_resource
from app.services.multimodal_provider import UPLOAD_ROOT, save_multimodal_upload

router = APIRouter(prefix="/multimodal", tags=["multimodal"])


def run_multimodal(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or "")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    return MultimodalAgent().run({
        **context,
        "user_message": message,
        "attachments": attachments,
        "session_id": payload.get("session_id") or context.get("session_id") or "",
        "image_url": payload.get("image_url") or context.get("image_url") or "",
        "image_base64": payload.get("image_base64") or context.get("image_base64") or "",
    })


def _session_id(payload: dict[str, Any]) -> str:
    return str(payload.get("session_id") or payload.get("sessionId") or "anonymous").strip() or "anonymous"


def _result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return result if isinstance(result, dict) else payload


def _knowledge_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    candidates = []
    for item in value:
        if not isinstance(item, dict):
            item = {"knowledge_point": str(item)}
        point = str(item.get("knowledge_point") or item.get("title") or "").strip()
        if not point:
            continue
        try:
            confidence = float(item.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        candidates.append({
            "course": str(item.get("course") or "").strip(),
            "knowledge_point": point,
            "parent": str(item.get("parent") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "prerequisites": item.get("prerequisites") if isinstance(item.get("prerequisites"), list) else [],
            "common_mistakes": item.get("common_mistakes") if isinstance(item.get("common_mistakes"), list) else [],
            "source_resource_id": str(item.get("source_resource_id") or "").strip(),
            "confidence": confidence,
            "review_status": "pending",
        })
    return candidates


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], tuple[str, str, bytes] | None]:
    msg = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    fields: dict[str, str] = {}
    file_part: tuple[str, str, bytes] | None = None
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename() or ""
        data = part.get_payload(decode=True) or b""
        if filename:
            file_part = (filename, part.get_content_type(), data)
        elif name:
            fields[name] = data.decode("utf-8", errors="replace")
    return fields, file_part


@router.post("/run")
async def run_multimodal_endpoint(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        fields, file_part = _parse_multipart(await request.body(), content_type)
        payload: dict[str, Any] = {"message": fields.get("message", ""), "session_id": fields.get("session_id", "")}
        if file_part:
            filename, mime, data = file_part
            saved = save_multimodal_upload(data, filename=filename, content_type=mime, session_id=payload["session_id"] or "anonymous")
            payload["attachments"] = [saved]
        return run_multimodal(payload)
    return run_multimodal(await request.json())


@router.post("/upload")
async def upload_multimodal(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            fields, file_part = _parse_multipart(await request.body(), content_type)
            if not file_part:
                raise ValueError("missing file")
            filename, mime, data = file_part
            return save_multimodal_upload(data, filename=filename, content_type=mime, session_id=fields.get("session_id") or "anonymous")
        payload = await request.json()
        image_base64 = str(payload.get("image_base64") or "")
        if image_base64.startswith("data:image/"):
            header, image_base64 = image_base64.split(",", 1)
            mime = header.removeprefix("data:").split(";", 1)[0]
        else:
            mime = str(payload.get("mime_type") or "image/png")
        return save_multimodal_upload(
            base64.b64decode(image_base64),
            filename=str(payload.get("filename") or "upload.png"),
            content_type=mime,
            session_id=str(payload.get("session_id") or "anonymous"),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/save-resource")
async def save_multimodal_resource(request: Request) -> dict[str, Any]:
    payload = await request.json()
    result = _result_payload(payload)
    candidate = result.get("resource_save_candidate") if isinstance(result.get("resource_save_candidate"), dict) else {}
    title = str(candidate.get("title") or result.get("title") or "图片学习资源").strip()
    resource_type = str(candidate.get("resource_type") or payload.get("resource_type") or payload.get("task_type") or "resource_bundle").strip()
    resource_id = str(candidate.get("id") or f"mm_{uuid.uuid4().hex}").strip()
    session_id = _session_id(payload)
    data = {
        "id": resource_id,
        "type": resource_type[:32],
        "title": title,
        "description": str(candidate.get("description") or "由图片 AI 学习功能生成，待人工确认。"),
        "content": json.dumps(result, ensure_ascii=False),
        "knowledge_points": result.get("weak_points") or result.get("target_knowledge_points") or result.get("possible_knowledge_points") or [],
        "tags": ["multimodal", "ai_generated", "pending_review"],
        "format": "json",
        "source": "agent_generated",
        "study_status": "new",
    }
    db = None
    try:
        db = SessionLocal()
        saved = upsert_resource(db, session_id, data)
        return {"status": "success", "saved": True, "resource_id": saved.id, "review_status": "pending"}
    except Exception as exc:
        return {"status": "failed", "saved": False, "warnings": [str(exc)]}
    finally:
        if db is not None:
            db.close()


@router.post("/knowledge-candidates")
async def multimodal_knowledge_candidates(request: Request) -> dict[str, Any]:
    payload = await request.json()
    result = _result_payload(payload)
    candidates = _knowledge_candidates(result.get("knowledge_candidates") or payload.get("knowledge_candidates"))
    return {"status": "success", "persisted": False, "candidates": candidates}


@router.get("/file/{file_id:path}")
def get_multimodal_file(file_id: str) -> FileResponse:
    path = (UPLOAD_ROOT / file_id).resolve()
    root = UPLOAD_ROOT.resolve()
    if root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)
