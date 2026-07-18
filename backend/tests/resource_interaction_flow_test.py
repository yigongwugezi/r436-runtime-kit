"""Resource-library interaction regression: ownership, updates, and refresh-safe reads."""
import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_fd, _path = tempfile.mkstemp(prefix="edu-resource-interaction-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"
os.environ["JWT_SECRET"] = "resource-interaction-test"

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.utils.auth import create_token


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="owner"), LearnerModel(id="other"),
            PersonalSubjectModel(id="math", learner_id="owner", name="Math"),
            PersonalSubjectModel(id="other-subject", learner_id="other", name="Other"),
            SessionModel(id="owner-session", learner_id="owner", subject_id="math"),
            SessionModel(id="other-session", learner_id="other", subject_id="other-subject"),
            ResourceModel(id="resource-1", session_id="owner-session", learner_id="owner", subject_id="math", type="lecture", title="Lecture", content="body"),
        ])
        db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        owner, other = _headers("owner"), _headers("other")
        scope = {"sessionId": "owner-session", "subjectId": "math"}
        assert client.get("/api/resources/resource-1", params=scope, headers=owner).status_code == 200
        assert client.post("/api/resources/resource-1/bookmark", params=scope, headers=owner).status_code == 200
        assert client.patch("/api/resources/resource-1/study-status", params=scope, json={"studyStatus": "completed"}, headers=owner).status_code == 200
        assert client.post("/api/resources/batch/bookmark", json={**scope, "resourceIds": ["resource-1"], "bookmarked": True}, headers=owner).status_code == 200
        assert client.post("/api/resources/batch/export", json={**scope, "resourceIds": ["resource-1"]}, headers=owner).status_code == 200
        assert client.delete("/api/resources/resource-1", params=scope, headers=other).status_code == 403
        assert client.delete("/api/resources/resource-1", params=scope, headers=owner).status_code == 200
        assert client.get("/api/resources/resource-1", params=scope, headers=owner).status_code == 404
    print("resource interaction flow: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_path).unlink(missing_ok=True)
