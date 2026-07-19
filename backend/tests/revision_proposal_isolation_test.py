"""Focused regression: pending revisions never replace a scoped active path."""
import os
import tempfile

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_fd, _db_path = tempfile.mkstemp(prefix="edu-revision-isolation-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearningPathModel, SessionModel
from app.db.repository import get_latest_learning_path
from app.services.conversation_state import _preserve_task_progress


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add(SessionModel(id="s", subject_id="outline"))
        db.add_all([
            LearningPathModel(id="outline-path", session_id="s", subject_id="outline", stages=[]),
            LearningPathModel(id="gravity-path", session_id="s", subject_id="gravity", stages=[]),
        ])
        db.commit()
        assert get_latest_learning_path(db, "s", "outline").id == "outline-path"
        assert get_latest_learning_path(db, "s", "gravity").id == "gravity-path"
        old = [{"task_id": "same", "status": "completed", "completed_at": 1}, {"task_id": "old", "status": "completed"}]
        new = [{"task_id": "same", "status": "pending"}, {"task_id": "new", "status": "pending"}]
        migrated = _preserve_task_progress(old, new)
        assert migrated[0]["status"] == "completed" and migrated[1]["status"] == "pending"
    finally:
        db.close()
        engine.dispose()
        os.unlink(_db_path)
    print("revision proposal isolation: PASS")


if __name__ == "__main__":
    main()
