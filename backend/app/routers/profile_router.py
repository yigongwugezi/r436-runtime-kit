"""Profile read endpoint — GET only, reads from DB."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.db.engine import SessionLocal
from app.db.repository import get_latest_profile
from app.utils.profile_normalizer import normalize_profile_dimensions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profile"])


@router.get("/api/profile")
def get_profile(sessionId: str = "") -> dict[str, Any]:
    if not sessionId:
        return {"status": "error", "data": None, "message": "sessionId required"}

    try:
        db = SessionLocal()
        snapshot = get_latest_profile(db, sessionId)
        if snapshot is None:
            return {
                "status": "success", "data": {
                    "id": sessionId, "dimensions": [], "weaknesses": [],
                    "preferences": {}, "source": "none",
                }, "message": "no profile yet",
            }
        dimensions = normalize_profile_dimensions(snapshot.dimensions)
        return {
            "status": "success",
            "data": {
                "id": sessionId,
                "dimensions": dimensions,
                "weaknesses": snapshot.weaknesses or [],
                "preferences": snapshot.preferences or {},
                "readiness_score": snapshot.readiness_score or 0.0,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            },
        }
    finally:
        db.close()
