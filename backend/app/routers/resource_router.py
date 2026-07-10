"""Resources read endpoint.

DEPRECATED (MAF-Refactor Phase 2): This router is no longer registered in main.py.
Its functionality has been migrated to ``product.py``. Kept for reference only.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.db.engine import SessionLocal
from app.db.repository import get_resources as repo_get_resources, get_bookmarked_ids

logger = logging.getLogger(__name__)
router = APIRouter(tags=["resources"])


@router.get("/api/resources")
def get_resources(sessionId: str = "") -> dict[str, Any]:
    if not sessionId:
        return {"status": "error", "data": [], "message": "sessionId required"}

    try:
        db = SessionLocal()
        rows = repo_get_resources(db, sessionId)
        bookmarks = get_bookmarked_ids(db, sessionId)
        items = [
            {
                "id": r.id, "type": r.type or "lecture", "title": r.title or "",
                "description": r.description or "", "content": r.content or "",
                "knowledge_points": r.knowledge_points or [],
                "tags": r.tags or [], "difficulty": r.difficulty or "medium",
                "estimated_minutes": r.estimated_minutes or 30,
                "format": r.format or "markdown",
                "bookmarked": r.id in bookmarks,
                "study_status": r.study_status or "new",
                "related_stage_id": str(r.related_stage_id or ""),
                "source": r.source or "system_inferred",
            }
            for r in rows
        ]
        return {"status": "success", "data": items}
    finally:
        db.close()
