"""Direct safety checks for dynamic revision and task-resource boundaries."""
import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_fd, _db_path = tempfile.mkstemp(prefix="edu-revision-safety-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "revision-safety-test-secret"

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.services.conversation_state import conversation_store
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
            PersonalSubjectModel(id="physics", learner_id="owner", name="Physics"),
            PersonalSubjectModel(id="other-subject", learner_id="other", name="Other"),
            SessionModel(id="s1", learner_id="owner", subject_id="math"),
            LearningPathModel(id="p1", session_id="s1", stages=[{"stage_id": "open", "tasks": [{"task_id": "task-1"}]}, {"stage_id": "locked", "tasks": [{"task_id": "task-2"}]}]),
            ResourceModel(id="r1", session_id="s1", type="lecture", title="x", content="x", related_stage_id="open", related_section_id="task-1", task_id="task-1"),
        ])
        db.commit()
    finally:
        db.close()
    conversation_store._sessions.clear()
    conversation_store.set_pending_revision("s1", [{"stage_id": "open", "tasks": [{"task_id": "task-1"}]}], {"summary": "x"}, path_id="p1", subject_id="math")
    revision_id = conversation_store.get_pending_revision("s1")["revision_id"]
    with TestClient(app) as client:
        owner, other = _headers("owner"), _headers("other")
        url = "/api/sections/task-1/generated-resources?sessionId=s1&subjectId=math&pathId=p1&stageId=open&taskId=task-1"
        assert client.get(url, headers=owner).status_code == 200
        assert client.get(url.replace("stageId=open", "stageId=locked").replace("task-1", "task-2"), headers=owner).status_code in (403, 404)
        assert client.get(url.replace("subjectId=math", "subjectId=physics"), headers=owner).status_code in (403, 409)
        assert client.get(url, headers=other).status_code == 403
        assert client.get("/api/sections/task-1/generated-resources?sessionId=s1", headers=owner).status_code == 400
        revision_url = f"/api/learning-path/s1/pending-revision?subjectId=math&pathId=p1"
        assert client.get(revision_url).status_code == 401
        assert client.get(revision_url, headers=other).status_code == 403
        assert client.post(f"/api/learning-path/s1/pending-revision/reject?subjectId=math&pathId=p1&revisionId=bad", headers=owner).status_code == 404
        assert client.post(f"/api/learning-path/s1/pending-revision/reject?subjectId=math&pathId=p1&revisionId={revision_id}", headers=owner).status_code == 200
        assert conversation_store.get_pending_revision("s1") is None
    print("dynamic revision safety: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
