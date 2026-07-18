"""Deterministic Competition Demo V1 core journey; no provider or network."""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, LearningEventModel, PracticeQuestionModel, QuizModel, ResourceModel, SessionModel
from app.db.repository import get_latest_learning_path, upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import assessment, product


def main() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(assessment.router, prefix="/api")
    app.dependency_overrides[assessment.require_auth] = lambda: AuthContext(learner_id="demo-learner")
    stages = [
        {"stage_id": "derivatives", "title": "导数基础", "tasks": [
            {"task_id": "lecture", "task_type": "lecture", "status": "completed"},
            {"task_id": "quiz", "task_type": "quiz", "status": "not_started"},
            {"task_id": "optional-map", "task_type": "mindmap", "optional": True, "status": "not_started"},
        ]},
        {"stage_id": "applications", "title": "导数应用", "tasks": [{"task_id": "next-lecture", "task_type": "lecture", "status": "not_started"}]},
    ]
    with patch.object(assessment, "SessionLocal", factory), patch.object(product, "SessionLocal", factory), \
         patch.object(assessment, "_trigger_post_submit_assessment") as post_assessment, \
         patch.object(assessment, "_create_assessment_processing_task", return_value=None), \
         patch.object(assessment, "_create_diagnosis_refresh_task", return_value=None):
        db = factory()
        db.add(SessionModel(id="demo-session", learner_id="demo-learner", subject_id="calculus"))
        upsert_learning_path(db, "demo-session", {"id": "demo-path", "stages": stages})
        db.add_all([
            QuizModel(id="demo-quiz", session_id="demo-session", path_id="demo-path", stage_id="derivatives", title="导数基础测验"),
            PracticeQuestionModel(question_id="q1", question_set_id="demo-quiz", session_id="demo-session", type="choice", stem="d/dx x²", correct="A"),
            ResourceModel(id="lecture-v1", session_id="demo-session", learner_id="demo-learner", subject_id="calculus", path_id="demo-path", related_stage_id="derivatives", task_id="lecture", type="lecture", title="导数讲义", content="导数描述瞬时变化率。"),
        ])
        db.commit(); db.close()

        client = TestClient(app)
        response = client.post("/api/quizzes/demo-quiz/submit", json={
            "sessionId": "demo-session", "pathId": "demo-path", "stageId": "derivatives", "taskId": "quiz",
            "idempotencyKey": "demo-submit", "answers": [{"questionId": "q1", "answer": "A"}],
        })
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert result["assessmentCompleted"] and result["pathTaskCompleted"] and result["stageCompleted"]
        assert result["nextStageUnlocked"] and result["pathProgress"]["nextTask"]["taskId"] == "next-lecture"
        assert client.post("/api/quizzes/demo-quiz/submit", json={
            "sessionId": "demo-session", "pathId": "demo-path", "stageId": "derivatives", "taskId": "quiz",
            "idempotencyKey": "demo-submit", "answers": [{"questionId": "q1", "answer": "A"}],
        }).json()["data"]["idempotentReplay"]
        assert post_assessment.call_count == 1

        db = factory()
        path = get_latest_learning_path(db, "demo-session")
        assert [stage["progressStatus"] for stage in product._apply_stage_progress(path.stages)] == ["completed", "current"]
        assert db.query(LearningEventModel).filter(LearningEventModel.event_type == "task_complete").count() == 1
        lecture = db.get(ResourceModel, "lecture-v1")
        assert lecture and lecture.content
        db.close()
    print("competition demo v1 e2e: PASS")


if __name__ == "__main__":
    main()
