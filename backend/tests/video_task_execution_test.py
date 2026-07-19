"""Focused video-task evidence and canonical completion regression."""
import sys
import time
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import Base, CurrentLearningPathModel, LearningEventModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.db.repository import upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import product
from app.services.workflow_tasks import workflow_task_manager


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
        upsert_learning_path(db, "s", {"id": "p", "subject_id": "sub", "estimatedDays": 35, "stages": [{"id": "stage", "days": days}]})
        db.add(CurrentLearningPathModel(learner_id="owner", session_id="s", subject_id="sub", path_id="p"))
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
    class FakeLectureClient:
        def chat(self, **_kwargs):
            return "# Canonical Video Title\n\n## Core concept\nA complete fallback lecture.\n\n## Summary\nReview the concept."

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine)
    app = FastAPI(); app.include_router(product.router, prefix="/api")
    app.dependency_overrides[product.require_auth] = lambda: AuthContext(learner_id="owner")
    with patch.object(product, "SessionLocal", factory):
        db = factory(); db.add_all([SessionModel(id="fallback-s", learner_id="owner", subject_id="fallback-sub"), PersonalSubjectModel(id="fallback-sub", learner_id="owner", name="x")])
        upsert_learning_path(db, "fallback-s", {"id": "fallback-p", "subject_id": "fallback-sub", "stages": [{"id": "stage", "days": [{"id": "stage_d1", "globalDayIndex": 1, "tasks": [{"id": "video-fallback", "type": "video", "title": "Canonical Video Title", "goal": "Watch the canonical video"}]}]}]})
        db.add(CurrentLearningPathModel(learner_id="owner", session_id="fallback-s", subject_id="fallback-sub", path_id="fallback-p"))
        db.add(ResourceModel(id="fallback-lecture", session_id="fallback-s", type="lecture", content="alternative text", related_section_id="video-fallback", task_id="video-fallback", resource_metadata={"deliveryMode": "video_fallback_lecture", "sourceTaskType": "video"})); db.commit(); db.close()
        payload = {"sessionId": "fallback-s", "subjectId": "fallback-sub", "pathId": "fallback-p", "stageId": "stage", "dayId": "stage_d1", "globalDayIndex": 1}
        client = TestClient(app)
        assert client.get("/api/learning-path/tasks/video-fallback/video-fallback/state", params=payload).json()["activeDeliveryMode"] == "video"
        assert client.post("/api/learning-path/tasks/video-fallback/video-fallback/lecture/ensure", json=payload).status_code == 409
        assert client.post("/api/learning-path/tasks/video-fallback/video-fallback-selected", json=payload).status_code == 200
        assert client.post("/api/learning-path/tasks/video-fallback/delivery-mode", json={**payload, "mode": "video_fallback_lecture"}).json()["data"]["activeDeliveryMode"] == "video_fallback_lecture"
        assert client.get("/api/learning-path/tasks/video-fallback/video-fallback/state", params=payload).json()["activeDeliveryMode"] == "video_fallback_lecture"
        assert client.post("/api/learning-path/tasks/video-fallback/delivery-mode", json={**payload, "mode": "video"}).json()["data"]["activeDeliveryMode"] == "video"
        assert client.post("/api/learning-path/tasks/video-fallback/delivery-mode", json={**payload, "mode": "video"}).json()["data"]["activeDeliveryMode"] == "video"
        canonical_payload, _ = product._video_fallback_payload("video-fallback", {**payload, "sectionTitle": "forged", "taskTitle": "forged"}, AuthContext(learner_id="owner"))
        assert canonical_payload["taskTitle"] == "Canonical Video Title"
        assert canonical_payload["sectionTitle"] == "Canonical Video Title"
        assert canonical_payload["sectionId"] == canonical_payload["taskId"] == "video-fallback"
        assert client.post("/api/sections/video-fallback/lecture/ensure", json={**payload, "taskId": "video-fallback", "taskType": "video"}).status_code == 409
        with patch.object(product, "_llm_client", return_value=FakeLectureClient()):
            started = client.post("/api/learning-path/tasks/video-fallback/video-fallback/lecture/ensure", json=payload)
            assert started.status_code == 200 and started.json()["status"] == "running", started.text
            workflow_id = started.json()["workflowId"]
            for _ in range(50):
                workflow = workflow_task_manager.get(workflow_id, "owner", "fallback-s")
                if workflow.status in {"completed", "failed"}:
                    break
                time.sleep(0.02)
            assert workflow.status == "completed" and workflow.result_available is True
        db = factory(); generated = db.query(ResourceModel).filter(ResourceModel.id == workflow.result["data"]["lecture"]["id"]).one()
        assert generated.content and generated.resource_metadata["deliveryMode"] == "video_fallback_lecture"
        assert generated.resource_metadata["originalTaskId"] == "video-fallback"
        assert generated.resource_metadata["canonicalScope"]["dayId"] == "stage_d1"; generated_id = generated.id; db.close()
        reused = client.post("/api/learning-path/tasks/video-fallback/video-fallback/lecture/ensure", json=payload)
        assert reused.status_code == 200 and reused.json()["status"] == "ready"
        assert client.post("/api/learning-path/tasks/video-fallback/delivery-mode", json={**payload, "mode": "video_fallback_lecture"}).json()["data"]["activeDeliveryMode"] == "video_fallback_lecture"
        assert client.get("/api/learning-path/tasks/video-fallback/video-fallback/state", params=payload).json()["lecture"]["id"] == generated_id
        assert client.post("/api/learning-path/tasks/video-fallback/complete", json=payload).status_code == 409
        assert client.post("/api/learning-path/tasks/video-fallback/video-fallback-lecture-opened", json=payload).status_code == 200
        completed = client.post("/api/learning-path/tasks/video-fallback/complete", json=payload)
        assert completed.status_code == 200 and completed.json()["data"]["taskId"] == "video-fallback"
        db = factory(); event = db.query(LearningEventModel).filter(LearningEventModel.event_type == "video_fallback_selected").one()
        assert event.metadata_["lectureResourceId"] == generated_id and event.metadata_["lectureContentReady"] is True; db.close()
    print("video fallback completion: PASS")


def recommendations_main():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine)
    app = FastAPI(); app.include_router(product.router, prefix="/api")
    app.dependency_overrides[product.require_auth] = lambda: AuthContext(learner_id="owner")
    with patch.object(product, "SessionLocal", factory):
        db = factory(); db.add_all([SessionModel(id="video-s", learner_id="owner", subject_id="video-sub"), PersonalSubjectModel(id="video-sub", learner_id="owner", name="x")])
        upsert_learning_path(db, "video-s", {"id": "video-p", "subject_id": "video-sub", "stages": [{"id": "stage", "days": [{"id": "stage_d2", "globalDayIndex": 2, "tasks": [{"id": "watch", "type": "watch_video", "title": "Big O"}]}]}]}); db.add(CurrentLearningPathModel(learner_id="owner", session_id="video-s", subject_id="video-sub", path_id="video-p")); db.commit(); db.close()
        payload = {"sessionId": "video-s", "subjectId": "video-sub", "pathId": "video-p", "stageId": "stage", "dayId": "stage_d2", "globalDayIndex": 2, "taskId": "watch", "resourceTypes": ["video"]}
        good = {"resources": [{"resource_type": "video", "title": "Big O", "url": "https://www.bilibili.com/video/BV1abc"}], "status": "completed", "warnings": []}
        with patch("app.services.section_resource_recommendations.SectionResourceRecommendationService.recommend", return_value=good) as search:
            first = TestClient(app).post("/api/resources/recommendations/for-learning", json=payload)
            assert first.status_code == 200 and first.json()["data"]["recommendations"]["presentationStatus"] == "new_search"
            assert search.call_count == 1
        with patch("app.services.section_resource_recommendations.SectionResourceRecommendationService.recommend", return_value={"resources": [], "status": "search_unavailable", "warnings": ["timeout"]}):
            stale = TestClient(app).post("/api/resources/recommendations/for-learning", json={**payload, "refresh": True})
            recommendation = stale.json()["data"]["recommendations"]
            assert recommendation["presentationStatus"] == "stale" and recommendation["resources"][0]["title"] == "Big O", recommendation
        with patch("app.services.section_resource_recommendations.SectionResourceRecommendationService.recommend", side_effect=AssertionError("persisted result must skip search")):
            restored = TestClient(app).post("/api/resources/recommendations/for-learning", json=payload)
            assert restored.json()["data"]["recommendations"]["presentationStatus"] == "persisted"
    print("video recommendation persistence: PASS")


if __name__ == "__main__": main(); fallback_main(); recommendations_main()
