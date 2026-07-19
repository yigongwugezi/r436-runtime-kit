"""Route-level regression for daily task IDs shared by GET and lecture ensure."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_db_file = Path(tempfile.gettempdir()) / "edu_learning_path_task_index_test.db"
if _db_file.exists():
    _db_file.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["LLM_PROVIDER"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearningPathModel, SessionModel
from app.main import app
from app.routers import workflows

SESSION_ID = "session_1784446310007_7d7aa03f-d55e-4aea-ae16-ff11c4c255ce"
SUBJECT_ID = "ps_afeab69a4002"
PATH_ID = f"path_{SESSION_ID}"
STAGE_ID = f"{PATH_ID}_s0"
TASK_ID = f"{STAGE_ID}_d1_t0"


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add(SessionModel(id=SESSION_ID, subject_id=SUBJECT_ID))
        db.add(LearningPathModel(
            id=PATH_ID, session_id=SESSION_ID, course_id=SUBJECT_ID, course_name="test",
            stages=[{"stage_id": STAGE_ID, "days": [{"day": 1, "tasks": [{"title": "legacy daily task"}]}]}],
        ))
        db.commit()
    finally:
        db.close()

    with patch.object(workflows, "_start", return_value=(SimpleNamespace(task_id="ensure-test"), False)):
        with TestClient(app) as client:
            path_response = client.get("/api/learning-path", params={"sessionId": SESSION_ID, "subjectId": SUBJECT_ID})
            assert path_response.status_code == 200, path_response.text
            task = path_response.json()["data"]["path"]["stages"][0]["days"][0]["tasks"][0]
            assert task["id"] == TASK_ID == task["task_id"]
            response = client.post(f"/api/sections/{TASK_ID}/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": SUBJECT_ID, "pathId": PATH_ID,
                "stageId": STAGE_ID, "taskId": TASK_ID,
            })
            assert response.status_code == 200, response.text
            assert response.json()["status"] in {"ready", "running"}
            scoped_wrong = client.post(f"/api/sections/{TASK_ID}/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": SUBJECT_ID, "pathId": PATH_ID,
                "stageId": "wrong-stage", "taskId": TASK_ID,
            })
            assert scoped_wrong.status_code == 409, scoped_wrong.text
            missing = client.post(f"/api/sections/missing/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": SUBJECT_ID, "pathId": PATH_ID,
                "stageId": STAGE_ID, "taskId": "missing",
            })
            assert missing.status_code == 404, missing.text
    print("learning path task index route tests: ok")


if __name__ == "__main__":
    main()
