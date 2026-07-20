"""Lecture ensure reuses a resource only when its task meaning is unchanged."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, CurrentLearningPathModel, ResourceModel, SessionModel
from app.db.repository import upsert_learning_path, upsert_resource
from app.middleware.auth import AuthContext
from app.routers import product, workflows


class FailingLLM:
    def chat(self, *_args, **_kwargs) -> str:
        raise RuntimeError("provider connection failed")


def main() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(product.router, prefix="/api")
    auth = AuthContext(learner_id="learner-a")
    app.dependency_overrides[product.get_auth] = lambda: auth
    session_id, subject_id, path_id, stage_id, task_id = "lecture-semantic-session", "subject-a", "path-a", "stage-a", "stable-task"
    base = {
        "sessionId": session_id, "subjectId": subject_id, "pathId": path_id, "stageId": stage_id,
        "dayId": f"{stage_id}_d1", "globalDayIndex": 1, "taskId": task_id, "taskType": "read_doc",
        "taskTitle": "Old outline", "taskDescription": "Old learning task", "learningObjectives": ["old objective"],
        "knowledgePoints": [{"name": "old concept"}], "stageTitle": "Stage", "pathVersion": "v1",
    }
    db = factory()
    try:
        db.add(SessionModel(id=session_id, learner_id="learner-a", subject_id=subject_id))
        upsert_learning_path(db, session_id, {"id": path_id, "subject_id": subject_id, "stages": [{"stage_id": stage_id, "days": [{"id": f"{stage_id}_d1", "day": 1, "globalDayIndex": 1, "tasks": [{"task_id": task_id, "title": "Old outline", "type": "read_doc", "dayId": f"{stage_id}_d1"}]}]}]})
        db.flush()
        db.add(CurrentLearningPathModel(learner_id="learner-a", session_id=session_id, subject_id=subject_id, path_id=path_id, path_version=1))
        fingerprint = product._lecture_semantic_fingerprint(base, auth.learner_id)
        upsert_resource(db, session_id, {
            "id": "lecture-old-resource", "type": "lecture", "title": "Old outline", "content": "old lecture body",
            "related_section_id": task_id, "task_id": task_id, "resource_metadata": {"semanticFingerprint": fingerprint},
        })
        db.commit()
    finally:
        db.close()

    with patch.object(workflows, "_start", return_value=(SimpleNamespace(task_id="new-lecture-workflow"), False)), \
         patch.object(product, "SessionLocal", factory), \
         patch.object(product, "_llm_client", return_value=FailingLLM()), \
         patch.object(product, "_inject_spark_images", side_effect=lambda text, _title: text), \
        TestClient(app) as client:
        first = client.post(f"/api/sections/{task_id}/lecture/ensure", json=base)
        assert first.status_code == 200 and first.json()["status"] == "ready", first.text
        assert first.json()["lecture"]["id"] == "lecture-old-resource"

        revised = {**base, "taskTitle": "New course outline", "taskDescription": "New learning task", "learningObjectives": ["new objective"], "knowledgePoints": [{"name": "new concept"}], "pathVersion": "v2"}
        pending = client.post(f"/api/sections/{task_id}/lecture/ensure", json=revised)
        assert pending.status_code == 200 and pending.json()["status"] == "running", pending.text

        revised_fingerprint = product._lecture_semantic_fingerprint(revised, auth.learner_id)
        generated = product._generate_section_lecture(task_id, {**revised, "sectionTitle": "New course outline", "sectionGoal": "new objective", "semanticFingerprint": revised_fingerprint})
        assert generated["data"]["lecture"]["content"]
        db = factory()
        try:
            generated_resources = db.query(ResourceModel).filter(ResourceModel.task_id == task_id).all()
            fallback = next(item for item in generated_resources if (item.resource_metadata or {}).get("semanticFingerprint") == revised_fingerprint)
            assert fallback.resource_metadata["used_fallback"] is True
            assert fallback.resource_metadata["generation_mode"] == "fallback"
        finally:
            db.close()
        ready = client.post(f"/api/sections/{task_id}/lecture/ensure", json=revised)
        assert ready.status_code == 200 and ready.json()["status"] == "ready", ready.text
        assert ready.json()["lecture"]["id"] != "lecture-old-resource"

    db = factory()
    try:
        resources = db.query(ResourceModel).filter(ResourceModel.task_id == task_id, ResourceModel.type == "lecture").all()
        assert len(resources) == 2
        assert {item.resource_metadata["semanticFingerprint"] for item in resources} == {fingerprint, revised_fingerprint}
        assert next(item for item in resources if item.id == "lecture-old-resource").content == "old lecture body"
    finally:
        db.close()
        engine.dispose()
    print("lecture semantic identity tests: PASS")


if __name__ == "__main__":
    main()
