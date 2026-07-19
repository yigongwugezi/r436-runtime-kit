"""Focused regression for persisted quiz-task execution."""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import Base, LearningEventModel, SessionModel
from app.db.repository import upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import assessment, product


def main():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine)
    app = FastAPI(); app.include_router(assessment.router, prefix="/api"); app.include_router(product.router, prefix="/api")
    app.dependency_overrides[assessment.require_auth] = lambda: AuthContext(learner_id="owner")
    app.dependency_overrides[product.require_auth] = lambda: AuthContext(learner_id="owner")
    with patch.object(assessment, "SessionLocal", factory), patch.object(product, "SessionLocal", factory), \
         patch.object(assessment, "_trigger_post_submit_assessment"), patch.object(assessment, "_create_assessment_processing_task", return_value=None), patch.object(assessment, "_create_diagnosis_refresh_task", return_value=None):
        db = factory(); db.add(SessionModel(id="s", learner_id="owner", subject_id="sub"))
        upsert_learning_path(db, "s", {"id": "p", "stages": [{"id": "stage", "days": [{"id": "d1", "globalDayIndex": 1, "tasks": [{"id": "quiz", "type": "do_quiz", "title": "Fractions"}]}]}]}); db.commit(); db.close()
        client = TestClient(app); scope = {"sessionId": "s", "subjectId": "sub", "pathId": "p", "stageId": "stage", "taskId": "quiz", "globalDayIndex": 1}
        ready = client.post("/api/learning-path/tasks/quiz/quiz/ensure", json=scope); assert ready.status_code == 200, ready.text
        quiz = ready.json()["data"]["quiz"]; assert len(quiz["questions"]) == 5 and "correctAnswer" not in str(quiz)
        assert client.post("/api/learning-path/tasks/quiz/quiz/ensure", json=scope).json()["data"]["quiz"]["quizId"] == quiz["quizId"]
        answers = [{"questionId": q["questionId"], "answer": "B"} for q in quiz["questions"]]
        low = client.post("/api/learning-path/tasks/quiz/quiz/submit", json={**scope, "quizId": quiz["quizId"], "answers": answers, "idempotencyKey": "low"}); assert low.status_code == 200 and not low.json()["data"]["passed"], low.text
        answers = [{"questionId": q["questionId"], "answer": answer} for q, answer in zip(quiz["questions"], ["C", "A", "B", "B", "A"])]
        high = client.post("/api/learning-path/tasks/quiz/quiz/submit", json={**scope, "quizId": quiz["quizId"], "answers": answers, "idempotencyKey": "high"}); assert high.status_code == 200 and high.json()["data"]["passed"]
        db = factory(); assert db.query(LearningEventModel).filter(LearningEventModel.event_type == "task_complete").count() == 1; db.close()
    print("learning path quiz execution: PASS")


if __name__ == "__main__": main()
