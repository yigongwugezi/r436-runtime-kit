"""GRADE Agent proxy — 直接转发到 GRADE Agent :8002"""
import logging, os
from pathlib import Path
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
from dotenv import load_dotenv; load_dotenv(_env)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/grade-proxy", tags=["grading"])
GRADER_URL = os.getenv("GRADER_URL", "http://localhost:8002")


class GradeRequest(BaseModel):
    question_id: str = ""
    question_type: str = "shortanswer"
    stem: str = ""
    options: list[str] = []
    correct: str = ""
    reference_answer: str = ""
    explanation: str = ""
    knowledge_points: list[str] = []
    student_answer: str = ""
    student_id: str = ""


@router.post("/assess")
def assess(req: GradeRequest):
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f"{GRADER_URL}/api/grade/assess", json=req.model_dump())
            if r.status_code == 200:
                return r.json()
            return {"error": r.text, "status": r.status_code}
    except Exception as e:
        return {"error": str(e), "status": 500}


@router.get("/stats/{student_id}")
def stats(student_id: str):
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{GRADER_URL}/api/grade/stats/{student_id}")
            if r.status_code == 200:
                return r.json()
            return {"error": r.text}
    except Exception as e:
        return {"error": str(e)}
