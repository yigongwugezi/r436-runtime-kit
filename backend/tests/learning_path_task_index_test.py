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
from app.db.models import Base, CurrentLearningPathModel, LearningPathModel, SessionModel
from app.main import app
from app.routers import workflows

SESSION_ID = "session_1784446310007_7d7aa03f-d55e-4aea-ae16-ff11c4c255ce"
SUBJECT_ID = "ps_afeab69a4002"
PATH_ID = "path_6ff3b5305c2ca98fd5a969b4663e56b1"
STAGE_ID = f"path_session_{SESSION_ID}_s0"
TASK_ID = f"{STAGE_ID}_d1_t0"


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add(SessionModel(id=SESSION_ID, subject_id=SUBJECT_ID))
        db.add(LearningPathModel(
            id=PATH_ID, session_id=SESSION_ID, subject_id=SUBJECT_ID, course_id=SUBJECT_ID, course_name="test",
            stages=[{"stage_id": STAGE_ID, "days": [{"id": f"{STAGE_ID}_d1", "day": 1, "globalDayIndex": 1, "tasks": [{"title": "persisted daily task", "type": "read_doc", "dayId": f"{STAGE_ID}_d1"}]}]}],
        ))
        db.flush()
        db.add(CurrentLearningPathModel(learner_id="", session_id=SESSION_ID, subject_id=SUBJECT_ID, path_id=PATH_ID, path_version=1))
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
                "stageId": STAGE_ID, "dayId": f"{STAGE_ID}_d1", "globalDayIndex": 1, "taskId": TASK_ID, "taskType": "read_doc",
            })
            assert response.status_code == 200, response.text
            assert response.json()["status"] in {"ready", "running"}
            scoped_wrong = client.post(f"/api/sections/{TASK_ID}/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": SUBJECT_ID, "pathId": PATH_ID,
                "stageId": "wrong-stage", "dayId": f"{STAGE_ID}_d1", "globalDayIndex": 1, "taskId": TASK_ID, "taskType": "read_doc",
            })
            assert scoped_wrong.status_code == 409, scoped_wrong.text
            missing = client.post(f"/api/sections/missing/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": SUBJECT_ID, "pathId": PATH_ID,
                "stageId": STAGE_ID, "dayId": f"{STAGE_ID}_d1", "globalDayIndex": 1, "taskId": "missing", "taskType": "read_doc",
            })
            assert missing.status_code == 404, missing.text
            wrong_subject = client.post(f"/api/sections/{TASK_ID}/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": "other-subject", "pathId": PATH_ID,
                "stageId": STAGE_ID, "dayId": f"{STAGE_ID}_d1", "globalDayIndex": 1, "taskId": TASK_ID, "taskType": "read_doc",
            })
            assert wrong_subject.status_code == 403, wrong_subject.text
            wrong_type = client.post(f"/api/sections/{TASK_ID}/lecture/ensure", json={
                "sessionId": SESSION_ID, "subjectId": SUBJECT_ID, "pathId": PATH_ID,
                "stageId": STAGE_ID, "dayId": f"{STAGE_ID}_d1", "globalDayIndex": 1, "taskId": TASK_ID, "taskType": "quiz_prac",
            })
            assert wrong_type.status_code == 409, wrong_type.text
    print("learning path task index route tests: ok")


if __name__ == "__main__":
    main()
