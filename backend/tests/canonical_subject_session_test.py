"""Focused regression coverage for deterministic subject learning sessions."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-canonical-session-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "canonical-session-test-secret"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, SessionModel
from app.main import app
from app.services.canonical_learning_session import resolve_canonical_learning_session
from app.utils.auth import create_token

SUBJECT = "ps_afeab69a4002"
NEW = "session_1784446310007_7d7aa03f-d55e-4aea-ae16-ff11c4c255ce"
OLD = "session_1784431530125_dfbc1360-2a32-4e5d-abdb-ba088ddb99aa"


def _path(path_id: str, session_id: str, updated_at: datetime) -> LearningPathModel:
    return LearningPathModel(
        id=path_id, session_id=session_id, stages=[{"id": "stage", "tasks": [{"id": "task"}]}],
        estimated_days=30, created_at=updated_at, updated_at=updated_at,
    )


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def main() -> None:
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="owner"), LearnerModel(id="other"),
            PersonalSubjectModel(id=SUBJECT, learner_id="owner", name="Data structures"),
            SessionModel(id=NEW, learner_id="owner", subject_id=SUBJECT, updated_at=now - timedelta(minutes=30)),
            # This chat session is newer, but its formal path is older.
            SessionModel(id=OLD, learner_id="owner", subject_id=SUBJECT, updated_at=now),
            _path(f"path_{OLD}", OLD, now - timedelta(minutes=20)),
            _path(f"path_{NEW}", NEW, now - timedelta(minutes=10)),
            SessionModel(id="new-chat", learner_id="owner", subject_id=SUBJECT, updated_at=now + timedelta(minutes=1)),
        ])
        db.commit()
        resolved = resolve_canonical_learning_session(db, "owner", SUBJECT)
        assert resolved and resolved["session_id"] == NEW
        assert resolved["path_id"] == f"path_{NEW}"
        assert resolved["source"] == "formal_learning_path"
        # Query order cannot affect the selection: updates, not row order, decide it.
        assert resolve_canonical_learning_session(db, "owner", SUBJECT)["session_id"] == NEW
    finally:
        db.close()

    with TestClient(app) as client:
        response = client.get("/api/subjects/session", params={"subject_id": SUBJECT}, headers=_headers("owner"))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["session_id"] == NEW and data["path_id"] == f"path_{NEW}"
        assert client.get("/api/subjects/session", params={"subject_id": SUBJECT}, headers=_headers("other")).json()["data"]["session_id"] is None

    db = SessionLocal()
    try:
        # An explicitly adopted newer formal path may become canonical.
        db.add(_path("adopted-path", OLD, now + timedelta(minutes=2)))
        db.commit()
        assert resolve_canonical_learning_session(db, "owner", SUBJECT)["session_id"] == OLD
    finally:
        db.close()
    print("canonical subject session: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
