"""Daily tasks router — stub endpoint for frontend compatibility."""

from fastapi import APIRouter

router = APIRouter(tags=["daily-tasks"])


@router.get("/api/daily-tasks/today")
def get_today_tasks(learnerId: str = "") -> dict:
    return {"tasks": [], "date": "", "totalMinutes": 0}
