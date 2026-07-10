"""Daily tasks router — stub endpoint for frontend compatibility.

DEPRECATED (MAF-Refactor Phase 2): This router is no longer registered in main.py.
Its functionality has been migrated to ``product.py``. Kept for reference only.
"""

from fastapi import APIRouter

router = APIRouter(tags=["daily-tasks"])


@router.get("/api/daily-tasks/today")
def get_today_tasks(learnerId: str = "") -> dict:
    return {"tasks": [], "date": "", "totalMinutes": 0}
