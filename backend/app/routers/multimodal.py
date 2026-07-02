"""Debug/test endpoint for MultimodalAgent."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.agents.multimodal_agent import MultimodalAgent

router = APIRouter(prefix="/multimodal", tags=["multimodal"])


@router.post("/run")
def run_multimodal(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or "")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    return MultimodalAgent().run({
        **context,
        "user_message": message,
        "attachments": attachments,
    })
