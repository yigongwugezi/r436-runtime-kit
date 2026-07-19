"""Completion regression for one canonical reading task and the next Day unlock."""
import os, tempfile
from pathlib import Path
os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_fd, _db_path = tempfile.mkstemp(prefix="edu-completion-", suffix=".db"); os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "completion-test-secret"
from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel, LearningEventModel
from app.main import app
from app.utils.auth import create_token

def main():
    session, subject, path, stage = "s", "subject", "path_s", "path_s_s0"
    t0, t1 = f"{stage}_d1_t0", f"{stage}_d2_t0"
    Base.metadata.create_all(engine); db = SessionLocal()
    try:
        db.add_all([LearnerModel(id="owner"), LearnerModel(id="other"), PersonalSubjectModel(id=subject, learner_id="owner", name="x"), SessionModel(id=session, learner_id="owner", subject_id=subject), LearningPathModel(id=path, session_id=session, subject_id=subject, estimated_days=2, stages=[{"id": stage, "days": [{"id": f"{stage}_d1", "globalDayIndex": 1, "tasks": [{"id": t0, "task_id": t0, "type": "read_doc", "mastery": 0}]}, {"id": f"{stage}_d2", "globalDayIndex": 2, "tasks": [{"id": t1, "task_id": t1, "type": "read_doc", "mastery": 0}]}]}]), ResourceModel(id="lecture", session_id=session, type="lecture", title="x", content="ready lecture", related_section_id=t0)])
        db.commit()
    finally: db.close()
    headers = lambda who: {"Authorization": f"Bearer {create_token(who, 'student')}"}
    payload = {"sessionId": session, "subjectId": subject, "pathId": path, "stageId": stage, "dayId": f"{stage}_d1", "globalDayIndex": 1}
    with TestClient(app) as client:
        first = client.post(f"/api/learning-path/tasks/{t0}/complete", json=payload, headers=headers("owner")); assert first.status_code == 200
        data = first.json()["data"]; assert data["taskStatus"] == "completed" and data["dayProgress"]["completed"] == 1 and data["nextTask"]["taskId"] == t1 and data["unlockedDay"] == 2
        assert data["nextTask"]["routeContext"]["globalDayIndex"] == 2
        refreshed = client.get("/api/learning-path", params={"sessionId": session, "subjectId": subject}).json()["data"]["path"]
        assert refreshed["overallProgress"] == 50 and refreshed["stages"][0]["days"][0]["tasks"][0]["status"] == "completed"
        assert refreshed["stages"][0]["days"][0]["progressStatus"] == "completed" and refreshed["stages"][0]["days"][1]["progressStatus"] == "current"
        assert client.post(f"/api/learning-path/tasks/{t0}/complete", json=payload, headers=headers("owner")).json()["data"]["pathTaskCompleted"] is False
        assert client.post(f"/api/learning-path/tasks/{t0}/complete", json={**payload, "globalDayIndex": 2}, headers=headers("owner")).status_code == 409
        assert client.post(f"/api/learning-path/tasks/{t0}/complete", json=payload, headers=headers("other")).status_code == 403
    db = SessionLocal()
    try:
        task = db.get(LearningPathModel, path).stages[0]["days"][0]["tasks"][0]
        assert task["status"] == "completed" and task["mastery"] == 0
        event = db.query(LearningEventModel).filter(LearningEventModel.event_type == "task_complete").one()
        assert event.metadata_["lectureResourceId"] == "lecture" and event.metadata_["evidenceType"] == "lecture_loaded_explicit_completion"
    finally: db.close()
    print("learning task completion: PASS")
if __name__ == "__main__":
    try: main()
    finally: engine.dispose(); Path(_db_path).unlink(missing_ok=True)
