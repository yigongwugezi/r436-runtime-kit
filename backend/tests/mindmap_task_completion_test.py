"""A canonical mind-map task completes only with its persisted resource."""
import os, tempfile
from pathlib import Path
os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_fd, _db_path = tempfile.mkstemp(prefix="edu-mindmap-completion-", suffix=".db"); os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "mindmap-completion-test-secret"
from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import Base, CurrentLearningPathModel, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.utils.auth import create_token

def main():
    session, subject, path, stage, day, task = "s", "subject", "path", "stage", "stage_d1", "mindmap"
    Base.metadata.create_all(engine); db = SessionLocal()
    try:
        db.add_all([LearnerModel(id="owner"), PersonalSubjectModel(id=subject, learner_id="owner", name="x"),
            SessionModel(id=session, learner_id="owner", subject_id=subject),
            LearningPathModel(id=path, session_id=session, subject_id=subject, estimated_days=1, stages=[{"id": stage, "days": [{"id": day, "globalDayIndex": 1, "tasks": [{"id": task, "task_id": task, "type": "mind_map"}]}]}])])
        db.commit()
        db.add_all([
            CurrentLearningPathModel(learner_id="owner", session_id=session, subject_id=subject, path_id=path),
            ResourceModel(id="map", session_id=session, type="mindmap", title="x", content="mindmap\n  root((x))\n    y", related_section_id=task)])
        db.commit()
    finally: db.close()
    payload = {"sessionId": session, "subjectId": subject, "pathId": path, "stageId": stage, "dayId": day, "globalDayIndex": 1, "evidenceType": "mindmap_viewed"}
    headers = {"Authorization": f"Bearer {create_token('owner', 'student')}"}
    with TestClient(app) as client:
        assert client.post(f"/api/learning-path/tasks/{task}/complete", json=payload, headers=headers).status_code == 409
        completed = client.post(f"/api/learning-path/tasks/{task}/complete", json={**payload, "resourceId": "map"}, headers=headers)
        assert completed.status_code == 200 and completed.json()["data"]["taskStatus"] == "completed", completed.text
    print("mindmap task completion: PASS")

if __name__ == "__main__":
    try: main()
    finally: engine.dispose(); Path(_db_path).unlink(missing_ok=True)
