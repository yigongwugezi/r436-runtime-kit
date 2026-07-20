"""Minimal HTTP regression coverage for resource ownership and subject scope."""
import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
handle, db_path = tempfile.mkstemp(prefix="edu-resource-auth-", suffix=".db")
os.close(handle)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["JWT_SECRET"] = "resource-auth-test-secret"

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.utils.auth import create_token


def headers(learner_id):
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="a"), LearnerModel(id="b"),
            PersonalSubjectModel(id="math", learner_id="a", name="Math"),
            PersonalSubjectModel(id="physics", learner_id="a", name="Physics"),
            PersonalSubjectModel(id="other", learner_id="b", name="Other"),
            SessionModel(id="math-s", learner_id="a", subject_id="math"),
            SessionModel(id="other-s", learner_id="b", subject_id="other"),
            SessionModel(id="multi-s", learner_id="a"),
            ResourceModel(id="math-r", session_id="math-s", type="lecture", title="Math", content="body", resource_metadata={"subject_id": "math"}),
            LearningPathModel(id="math-p", session_id="math-s", stages=[{"id": "stage-1", "nodes": [{"id": "task-1"}]}]),
        ])
        db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        a, b = headers("a"), headers("b")
        assert client.get("/api/resources?sessionId=math-s&subjectId=math").status_code == 401
        assert client.get("/api/resources/math-r?sessionId=math-s&subjectId=math").status_code == 401
        assert client.get("/api/knowledge-graph?sessionId=math-s&subjectId=math").status_code == 401
        assert client.patch("/api/learning-path/nodes/task-1", json={"sessionId": "math-s", "pathId": "math-p", "status": "completed"}).status_code == 401
        assert client.post("/api/resources/import-from-kb", json={"sessionId": "math-s", "subjectId": "math"}).status_code == 401
        assert client.post("/api/sections/task-1/generate-all", json={"sessionId": "math-s", "subjectId": "math", "sectionTitle": "Task"}).status_code == 401
        assert client.post("/api/sections/task-1/resources/generate", json={"sessionId": "math-s", "subjectId": "math", "resourceType": "summary_card"}).status_code == 401
        assert client.get("/api/resources?sessionId=math-s&subjectId=math", headers=a).status_code == 200
        assert client.get("/api/resources/math-r?sessionId=math-s&subjectId=math", headers=a).status_code == 200
        assert client.get("/api/knowledge-graph?sessionId=math-s&subjectId=math", headers=a).status_code == 200
        assert client.get("/api/knowledge-graph?sessionId=math-s&subjectId=math", headers=b).status_code == 403
        assert client.get("/api/resources?sessionId=other-s&subjectId=other", headers=a).status_code == 403
        assert client.get("/api/resources/math-r?sessionId=math-s&subjectId=math", headers=b).status_code == 403
        assert client.get("/api/resources?sessionId=multi-s", headers=a).status_code == 400
        assert client.post("/api/resources/generate", json={"sessionId": "math-s", "subjectId": "math", "pathId": "bad", "topic": "x", "resourceType": "lecture"}, headers=a).status_code == 403
        db = SessionLocal()
        try:
            assert db.get(LearningPathModel, "bad") is None
        finally:
            db.close()
    print("resource authorization scope: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)
