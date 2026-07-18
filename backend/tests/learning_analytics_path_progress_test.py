"""Persistent LearningPathModel progress exposed through analytics."""

from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "ahocorasick" not in sys.modules:
    sys.modules["ahocorasick"] = types.SimpleNamespace(
        Automaton=type("Automaton", (), {"add_word": lambda *_: None, "make_automaton": lambda *_: None, "iter": lambda *_: ()})
    )
_handle, _db_path = tempfile.mkstemp(prefix="edu-path-analytics-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "path-analytics-test-secret"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningEventModel, LearningPathModel, PersonalSubjectModel, SessionModel
from app.main import app
from app.routers import product
from app.utils.auth import create_token


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _seed() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="learner-a"), LearnerModel(id="learner-b"),
            PersonalSubjectModel(id="math", learner_id="learner-a", name="Math"),
            PersonalSubjectModel(id="other", learner_id="learner-b", name="Other"),
            SessionModel(id="session-a", learner_id="learner-a", subject_id="math"),
            SessionModel(id="session-b", learner_id="learner-b", subject_id="other"),
            LearningPathModel(id="path-a", session_id="session-a", stages=[
                {"id": "s1", "title": "第一阶段", "tasks": [
                    {"id": "lecture-1", "title": "极限的定义", "type": "lecture", "section_id": "lecture-1"},
                    {"id": "optional-1", "title": "选做", "type": "practice", "optional": True},
                ]},
                {"id": "s2", "title": "第二阶段", "tasks": [{"id": "quiz-2", "title": "阶段练习", "type": "quiz"}]},
                {"id": "s3", "title": "空阶段", "tasks": []},
            ]),
            LearningPathModel(id="path-complete", session_id="session-a", stages=[
                {"id": "c1", "tasks": [{"id": "done", "status": "completed"}]},
            ]),
        ])
        db.commit()
    finally:
        db.close()


def _analytics(client: TestClient, path_id: str = "path-a") -> dict:
    response = client.get(f"/api/learning-analytics?sessionId=session-a&subjectId=math&pathId={path_id}", headers=_headers("learner-a"))
    assert response.status_code == 200, response.text
    return response.json()["data"]["pathProgress"]


def main() -> None:
    _seed()
    product.conversation_store.get("session-a").last_result = {"learning_path": [{"id": "wrong"}], "currentStageIndex": 99}
    with TestClient(app) as client:
        before = _analytics(client)
        assert before["totalStageCount"] == 3 and before["currentStageId"] == "s1"
        assert before["totalRequiredTaskCount"] == 2 and before["completedRequiredTaskCount"] == 0
        assert before["nextTask"]["taskId"] == "lecture-1" and before["nextTask"]["accessible"]
        assert client.get("/api/learning-analytics?sessionId=session-b&subjectId=other&pathId=path-a", headers=_headers("learner-a")).status_code == 403
        product.update_node_progress("lecture-1", {"sessionId": "session-a", "subjectId": "math", "pathId": "path-a", "status": "mastered", "mastery": 100})
        after = _analytics(client)
        assert after["completedRequiredTaskCount"] == 1 and after["completedStageCount"] == 1
        assert after["currentStageId"] == "s2" and after["nextTask"]["taskId"] == "quiz-2"
        product.update_node_progress("lecture-1", {"sessionId": "session-a", "subjectId": "math", "pathId": "path-a", "status": "mastered", "mastery": 100})
        db = SessionLocal()
        try:
            assert db.query(LearningEventModel).filter(LearningEventModel.event_type == "task_complete").count() == 1
        finally:
            db.close()
        product.update_node_progress("quiz-2", {"sessionId": "session-a", "subjectId": "math", "pathId": "path-a", "status": "completed", "mastery": 100})
    with TestClient(app) as client:
        empty_current = _analytics(client)
        assert empty_current["currentStageId"] == "s3" and not empty_current["pathCompleted"] and empty_current["nextTask"] is None
        complete = _analytics(client, "path-complete")
        assert complete["pathCompleted"] and complete["nextTask"] is None
        recent = client.get("/api/learning-analytics?sessionId=session-a&subjectId=math", headers=_headers("learner-a")).json()["data"]["recentEvents"]
        assert any(event["event"] == "task_complete" for event in recent)
    print("learning analytics path progress: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        try:
            Path(_db_path).unlink(missing_ok=True)
        except PermissionError:
            pass
