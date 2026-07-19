"""Focused video-task evidence and canonical completion regression."""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import Base, LearningEventModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.db.repository import upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import product


def main():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine)
    app = FastAPI(); app.include_router(product.router, prefix="/api")
    app.dependency_overrides[product.require_auth] = lambda: AuthContext(learner_id="owner")
    with patch.object(product, "SessionLocal", factory):
        db = factory(); db.add_all([SessionModel(id="s", learner_id="owner", subject_id="sub"), PersonalSubjectModel(id="sub", learner_id="owner", name="x")])
        tasks = [{"id": "read", "type": "read_doc"}, {"id": "video", "type": "video"}, {"id": "quiz", "type": "quiz_prac"}]
        tasks.extend({"id": f"later-{i}", "type": "read_doc"} for i in range(32))
        days = [{"id": "stage_d1", "globalDayIndex": 1, "tasks": [tasks[0]]}, {"id": "stage_d2", "globalDayIndex": 2, "tasks": [tasks[1]]}, {"id": "stage_d3", "globalDayIndex": 3, "tasks": [tasks[2]]}]
        days.extend({"id": f"stage_d{i + 4}", "globalDayIndex": i + 4, "tasks": [tasks[i + 3]]} for i in range(32))
        upsert_learning_path(db, "s", {"id": "p", "estimatedDays": 35, "stages": [{"id": "stage", "days": days}]})
        db.add(ResourceModel(id="read-lecture", session_id="s", type="lecture", content="ready", related_section_id="read"))
        db.commit(); db.close()
        client = TestClient(app)
        base = {"sessionId": "s", "subjectId": "sub", "pathId": "p", "stageId": "stage"}
        reading = client.post("/api/learning-path/tasks/read/complete", json={**base, "dayId": "stage_d1", "globalDayIndex": 1})
        assert reading.status_code == 200, reading.text
        assert client.post("/api/learning-path/tasks/video/complete", json={**base, "dayId": "stage_d2", "globalDayIndex": 2}).status_code == 409
        opened = client.post("/api/learning-path/tasks/video/video-opened", json={**base, "dayId": "stage_d2", "globalDayIndex": 2, "resourceUrl": "https://www.youtube.com/watch?v=abc"})
        assert opened.status_code == 200 and opened.json()["data"]["recorded"]
        assert not client.post("/api/learning-path/tasks/video/video-opened", json={**base, "dayId": "stage_d2", "globalDayIndex": 2, "resourceUrl": "https://www.youtube.com/watch?v=abc"}).json()["data"]["recorded"]
        completed = client.post("/api/learning-path/tasks/video/complete", json={**base, "dayId": "stage_d2", "globalDayIndex": 2})
        assert completed.status_code == 200, completed.text
        data = completed.json()["data"]
        assert data["dayProgress"] == {"dayId": "stage_d2", "globalDayIndex": 2, "completed": 1, "total": 1}
        assert data["nextTask"]["taskId"] == "quiz" and data["unlockedDay"] == 3
        assert not client.post("/api/learning-path/tasks/video/complete", json={**base, "dayId": "stage_d2", "globalDayIndex": 2}).json()["data"]["pathTaskCompleted"]
        assert client.post("/api/learning-path/tasks/quiz/complete", json={**base, "dayId": "stage_d3", "globalDayIndex": 3}).status_code == 409
        db = factory(); persisted = db.get(LearningPathModel, "p")
        assert sum(task.get("status") == "completed" for day in persisted.stages[0]["days"] for task in day["tasks"]) == 2
        assert len([task for day in persisted.stages[0]["days"] for task in day["tasks"]]) == 35
        events = db.query(LearningEventModel).all()
        opened_event = next(event for event in events if event.event_type == "video_opened")
        assert opened_event.metadata_["learnerId"] == "owner" and opened_event.metadata_["sessionId"] == "s"
        assert opened_event.metadata_["subjectId"] == "sub" and opened_event.metadata_["pathId"] == "p"
        assert opened_event.metadata_["stageId"] == "stage" and opened_event.metadata_["dayId"] == "stage_d2"
        assert opened_event.metadata_["taskId"] == "video" and opened_event.metadata_["resourceUrl"].startswith("https://") and opened_event.metadata_["timestamp"]
        assert db.query(LearningEventModel).filter(LearningEventModel.event_type == "task_complete").count() == 2; db.close()
    print("video task execution: PASS")


def fallback_main():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine)
    app = FastAPI(); app.include_router(product.router, prefix="/api")
    app.dependency_overrides[product.require_auth] = lambda: AuthContext(learner_id="owner")
    with patch.object(product, "SessionLocal", factory):
        db = factory(); db.add_all([SessionModel(id="fallback-s", learner_id="owner", subject_id="fallback-sub"), PersonalSubjectModel(id="fallback-sub", learner_id="owner", name="x")])
        upsert_learning_path(db, "fallback-s", {"id": "fallback-p", "stages": [{"id": "stage", "days": [{"id": "stage_d1", "globalDayIndex": 1, "tasks": [{"id": "video-fallback", "type": "video"}]}]}]})
        db.add(ResourceModel(id="fallback-lecture", session_id="fallback-s", type="lecture", content="alternative text", related_section_id="video-fallback")); db.commit(); db.close()
        payload = {"sessionId": "fallback-s", "subjectId": "fallback-sub", "pathId": "fallback-p", "stageId": "stage", "dayId": "stage_d1", "globalDayIndex": 1}
        client = TestClient(app)
        assert client.post("/api/learning-path/tasks/video-fallback/video-fallback-selected", json=payload).status_code == 200
        completed = client.post("/api/learning-path/tasks/video-fallback/complete", json=payload)
        assert completed.status_code == 200 and completed.json()["data"]["taskId"] == "video-fallback"
    print("video fallback completion: PASS")


if __name__ == "__main__": main(); fallback_main()
