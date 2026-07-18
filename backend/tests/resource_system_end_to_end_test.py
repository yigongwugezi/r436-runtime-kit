"""Offline resource-system journey using a temporary SQLite database and mock LLM."""
import os
import tempfile
from pathlib import Path

os.environ.update({"EDUAGENT_SKIP_ENV_FILE": "1", "LLM_PROVIDER": "mock", "JWT_SECRET": "resource-e2e-test"})
_fd, _path = tempfile.mkstemp(prefix="edu-resource-e2e-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.routers import product
from app.utils.auth import create_token


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="a"), LearnerModel(id="b"),
            PersonalSubjectModel(id="math", learner_id="a", name="Math"),
            PersonalSubjectModel(id="physics", learner_id="a", name="Physics"),
            PersonalSubjectModel(id="b-subject", learner_id="b", name="Other"),
            SessionModel(id="s", learner_id="a", subject_id="math"),
            LearningPathModel(id="p", session_id="s", stages=[
                {"id": "current", "nodes": [{"id": "lecture-task", "type": "lecture"}]},
                {"id": "locked", "nodes": [{"id": "locked-task", "type": "lecture"}]},
            ]),
        ])
        db.commit()
    finally:
        db.close()

    payload = {"sessionId": "s", "learnerId": "a", "subjectId": "math", "pathId": "p", "stageId": "current", "topic": "derivative", "difficulty": "medium", "operation": "generate", "mode": "general_resource_generation"}
    lecture = product._generate_general_resource({**payload, "resourceType": "lecture"})["data"]["resource"]
    assert lecture["content"].strip()
    assert product._generate_general_resource({**payload, "resourceType": "lecture"})["data"]["resource"]["id"] == lecture["id"]
    mindmap = product._generate_general_resource({**payload, "resourceType": "mindmap"})["data"]["resource"]
    assert mindmap["mermaidDef"].startswith("mindmap")

    db = SessionLocal()
    try:
        db.add(ResourceModel(id="locked-resource", session_id="s", learner_id="a", subject_id="math", path_id="p", related_stage_id="locked", task_id="locked-task", type="lecture", title="Locked", content="body"))
        db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        a, b = _headers("a"), _headers("b")
        scope = {"sessionId": "s", "subjectId": "math", "pathId": "p", "stageId": "current"}
        assert client.get(f"/api/resources/{lecture['id']}", params=scope, headers=a).status_code == 200
        assert client.get("/api/resources/locked-resource", params={**scope, "stageId": "locked"}, headers=a).status_code == 403
        saved = client.post("/api/resources/search-results/save", json={**scope, "query": "derivative", "resource": {"title": "Open lesson", "url": "https://example.org/lesson", "resource_type": "article", "snippet": "lesson"}}, headers=a)
        assert saved.status_code == 200
        resource_id = saved.json()["data"]["resourceId"]
        assert client.get("/api/resources", params={"sessionId": "s", "subjectId": "math"}, headers=a).status_code == 200
        assert client.post(f"/api/resources/{resource_id}/bookmark", params={"sessionId": "s", "subjectId": "math"}, headers=a).status_code == 200
        assert client.patch(f"/api/resources/{resource_id}/study-status", params={"sessionId": "s", "subjectId": "math"}, json={"studyStatus": "completed"}, headers=a).status_code == 200
        assert client.get(f"/api/resources/{resource_id}", params={"sessionId": "s", "subjectId": "math"}, headers=b).status_code == 403
        assert client.delete(f"/api/resources/{resource_id}", params={"sessionId": "s", "subjectId": "math"}, headers=b).status_code == 403
        assert client.delete(f"/api/resources/{resource_id}", params={"sessionId": "s", "subjectId": "math"}, headers=a).status_code == 200
    print("resource system end-to-end: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_path).unlink(missing_ok=True)
