"""Learning path read endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.db.engine import SessionLocal
from app.db.repository import get_latest_learning_path

logger = logging.getLogger(__name__)
router = APIRouter(tags=["learning-path"])


@router.get("/api/learning-path")
def get_learning_path(sessionId: str = "") -> dict[str, Any]:
    if not sessionId:
        return {"status": "error", "data": None, "message": "sessionId required"}

    try:
        db = SessionLocal()
        path = get_latest_learning_path(db, sessionId)
        if path is None:
            return {
                "status": "success", "data": {
                    "id": f"path_{sessionId}", "stages": [], "source": "none",
                },
            }
        return {
            "status": "success",
            "data": {
                "id": path.id,
                "course_id": path.course_id,
                "course_name": path.course_name,
                "description": path.description or "",
                "stages": path.stages or [],
                "overall_progress": path.overall_progress or 0,
                "estimated_days": path.estimated_days or 14,
                "created_at": path.created_at.isoformat() if path.created_at else None,
            },
        }
    finally:
        db.close()
