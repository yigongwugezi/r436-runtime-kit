"""Focused lecture task regression checks; no real provider or database."""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, SessionModel
from app.db.repository import get_latest_learning_path, upsert_learning_path
from app.middleware.auth import AuthContext
from app.routers import product


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def chat(self, messages, **_kwargs) -> str:
        self.calls += 1
        self.prompts.append(messages[-1]["content"])
        return "# 链表任务\n\n这是可持久化的讲义正文，用于理解节点和指针之间的关系。"


def main() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(product.router, prefix="/api")
    fake = FakeLLM()
    stages = [
        {"stage_id": "s1", "title": "链表基础", "tasks": [{"task_id": "t1", "title": "链表讲义", "status": "not_started"}]},
        {"stage_id": "s2", "title": "链表进阶", "tasks": [{"task_id": "t2", "title": "进阶讲义", "status": "not_started"}]},
    ]
    with patch.object(product, "SessionLocal", factory), \
         patch.object(product, "_llm_client", return_value=fake), \
         patch.object(product, "_inject_spark_images", side_effect=lambda text, _title: text):
        db = factory()
        try:
            upsert_learning_path(db, "lecture-session", {"id": "path-1", "stages": stages})
            db.get(SessionModel, "lecture-session").learner_id = "learner-a"
            db.commit()
        finally:
            db.close()
        client = TestClient(app)
        params = {"sessionId": "lecture-session", "pathId": "path-1", "stageId": "s1", "taskId": "t1"}
        assert client.get("/api/sections/t1/lecture", params=params).json()["data"]["lecture"] is None
        payload = {**params, "sectionTitle": "链表讲义", "sectionGoal": "理解节点", "knowledgePoints": [{"name": "指针"}]}
        created = client.post("/api/sections/t1/lecture/generate", json=payload)
        assert created.status_code == 200 and created.json()["data"]["lecture"]["content"]
        assert fake.calls == 1
        repeated = client.post("/api/sections/t1/lecture/generate", json=payload)
        assert repeated.status_code == 200 and fake.calls == 1
        refreshed = TestClient(app).get("/api/sections/t1/lecture", params=params)
        assert refreshed.status_code == 200 and refreshed.json()["data"]["lecture"]["content"]
        locked = client.get("/api/sections/t2/lecture", params={**params, "stageId": "s2", "taskId": "t2"})
        assert locked.status_code == 403
        app.dependency_overrides[product.get_auth] = lambda: AuthContext(learner_id="learner-b")
        assert client.get("/api/sections/t1/lecture", params=params).status_code == 403
        app.dependency_overrides.clear()
        tutor = client.post("/api/sections/t1/tutor/ask", json={
            **payload, "question": "这节课的重点是什么？", "lectureExcerpt": created.json()["data"]["lecture"]["content"],
        })
        assert tutor.status_code == 200 and tutor.json()["data"]["reply"]
        assert any("阶段 s1；任务 t1" in prompt for prompt in fake.prompts)
        completed = client.patch("/api/learning-path/nodes/t1", json={"sessionId": "lecture-session", "status": "mastered", "mastery": 100})
        assert completed.status_code == 200
        db = factory()
        try:
            path = get_latest_learning_path(db, "lecture-session")
            assert path and path.stages[0]["tasks"][0]["status"] == "mastered"
            assert product._apply_stage_progress(path.stages)[1]["progressStatus"] == "current"
        finally:
            db.close()
    print("focused lecture task tests: ok")


if __name__ == "__main__":
    main()
