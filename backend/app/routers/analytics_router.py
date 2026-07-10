"""Learning analytics read endpoint.

DEPRECATED (MAF-Refactor Phase 2): This router is no longer registered in main.py.
Its functionality has been migrated to ``product.py``. Kept for reference only.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.db.engine import SessionLocal
from app.db.repository import get_event_analytics

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])


@router.get("/api/analytics")
def get_analytics(sessionId: str = "") -> dict[str, Any]:
    if not sessionId:
        return {"status": "error", "data": None, "message": "sessionId required"}

    try:
        db = SessionLocal()
        analytics = get_event_analytics(db, sessionId)
        return {"status": "success", "data": analytics}
    finally:
        db.close()
