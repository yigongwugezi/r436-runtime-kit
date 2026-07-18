"""API regression: a graded path quiz completes exactly its linked task once."""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, LearningEventModel, PracticeQuestionModel, QuizModel, SessionModel
from app.db.repository import get_latest_learning_path, upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import assessment, product


def main() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(assessment.router, prefix="/api")
    app.dependency_overrides[assessment.require_auth] = lambda: AuthContext(learner_id="learner-a")
    stages = [
        {"stage_id": "s1", "tasks": [
            {"task_id": "lecture", "task_type": "lecture", "status": "completed"},
            {"task_id": "quiz", "task_type": "quiz", "status": "not_started"},
        ]},
        {"stage_id": "s2", "tasks": [{"task_id": "next", "task_type": "lecture", "status": "not_started"}]},
        {"stage_id": "s3", "tasks": [{"task_id": "later", "task_type": "lecture", "status": "not_started"}]},
    ]
    with patch.object(assessment, "SessionLocal", factory), patch.object(product, "SessionLocal", factory), \
         patch.object(assessment, "_trigger_post_submit_assessment"), \
         patch.object(assessment, "_create_assessment_processing_task", return_value=None), \
         patch.object(assessment, "_create_diagnosis_refresh_task", return_value=None):
        db = factory()
        db.add(SessionModel(id="session", learner_id="learner-a", subject_id="subject"))
        upsert_learning_path(db, "session", {"id": "path", "stages": stages})
        db.add(QuizModel(id="quiz-set", session_id="session", path_id="path", stage_id="s1"))
        db.add(PracticeQuestionModel(question_id="q1", question_set_id="quiz-set", session_id="session", type="choice", stem="x", correct="A"))
        db.commit()
        db.close()
        client = TestClient(app)
        payload = {"sessionId": "session", "pathId": "path", "stageId": "s1", "taskId": "quiz", "idempotencyKey": "once", "answers": [{"questionId": "q1", "answer": "A"}]}
        result = client.post("/api/quizzes/quiz-set/submit", json=payload)
        assert result.status_code == 200, result.text
        data = result.json()["data"]
        assert data["assessmentCompleted"] and data["pathTaskCompleted"] and data["stageCompleted"] and data["nextStageUnlocked"]
        assert data["pathProgress"]["nextTask"]["taskId"] == "next"
        replay = client.post("/api/quizzes/quiz-set/submit", json=payload)
        assert replay.status_code == 200 and replay.json()["data"]["idempotentReplay"]
        db = factory()
        path = get_latest_learning_path(db, "session")
        assert path.stages[0]["tasks"][1]["status"] == "completed"
        assert [s["progressStatus"] for s in product._apply_stage_progress(path.stages)] == ["completed", "current", "locked"]
        assert db.query(LearningEventModel).filter(LearningEventModel.event_type == "task_complete").count() == 1
        db.close()
    print("assessment path completion flow: ok")


if __name__ == "__main__":
    main()
