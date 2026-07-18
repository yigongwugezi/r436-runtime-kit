import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
os.environ["LLM_PROVIDER"] = "mock"
handle, db_path = tempfile.mkstemp(prefix="resource-versions-", suffix=".db")
os.close(handle)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.utils.auth import create_token


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([LearnerModel(id="learner"), PersonalSubjectModel(id="subject", learner_id="learner", name="Math"), SessionModel(id="session", learner_id="learner", subject_id="subject"), ResourceModel(id="v1", session_id="session", learner_id="learner", subject_id="subject", type="mindmap", title="Topic", content="old", knowledge_points=["Topic"], resource_metadata={"resource_type": "mindmap"})])
        db.commit()
    finally:
        db.close()
    headers = {"Authorization": f"Bearer {create_token('learner', 'student')}"}
    with TestClient(app) as client:
        first = client.post("/api/resources/v1/regenerate", json={"sessionId": "session", "subjectId": "subject", "operationId": "op-1"}, headers=headers)
        assert first.status_code == 200 and first.json()["data"]["generationVersion"] == 2
        v2 = first.json()["data"]["resourceId"]
        assert client.post("/api/resources/v1/regenerate", json={"sessionId": "session", "subjectId": "subject", "operationId": "op-1"}, headers=headers).json()["data"]["resourceId"] == v2
        second = client.post(f"/api/resources/{v2}/regenerate", json={"sessionId": "session", "subjectId": "subject", "operationId": "op-2"}, headers=headers)
        assert second.status_code == 200 and second.json()["data"]["generationVersion"] == 3
        db = SessionLocal()
        try:
            rows = {row.id: row for row in db.query(ResourceModel).all()}
            assert rows["v1"].generation_version == 1 and rows["v1"].supersedes_resource_id is None and rows["v1"].content == "old"
            assert rows[v2].supersedes_resource_id == "v1"
            assert rows[second.json()["data"]["resourceId"]].supersedes_resource_id == v2
        finally:
            db.close()
    print("resource regeneration versioning: PASS")


if __name__ == "__main__":
    try: main()
    finally:
        engine.dispose(); Path(db_path).unlink(missing_ok=True)
