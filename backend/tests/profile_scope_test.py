"""Regression check for the profile read fallback's canonical session scope."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _path = tempfile.mkstemp(prefix="edu-profile-scope-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_path).as_posix()}"

from fastapi.testclient import TestClient

from app.db.engine import engine
from app.main import app
from app.services.conversation_state import conversation_store


def main() -> None:
    session_id = "profile-scope-session"
    state = conversation_store.get(session_id)
    state.last_result = {"learning_path": []}
    try:
        with TestClient(app) as client:
            response = client.get("/api/profile", params={"sessionId": session_id, "subjectId": "profile-scope-subject"})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["profile"]["id"] == session_id
    finally:
        conversation_store._sessions.pop(session_id, None)
        engine.dispose()
        os.unlink(_path)
    print("profile scope: PASS")


if __name__ == "__main__":
    main()
