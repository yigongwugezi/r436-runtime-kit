"""Route regression for generated resources on canonical daily tasks."""

import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_fd, _db_path = tempfile.mkstemp(prefix="edu-generated-resources-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "generated-resources-test-secret"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, ResourceModel, SessionModel
from app.main import app
from app.utils.auth import create_token

SESSION = "session_1784446310007_7d7aa03f-d55e-4aea-ae16-ff11c4c255ce"
PATH = f"path_{SESSION}"
TASK = f"{PATH}_s0_d1_t0"
STAGE = f"{PATH}_s0"
DAY = f"{STAGE}_d1"


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _url(task_id: str = TASK, **params: str | int) -> str:
    base = {
        "sessionId": SESSION, "subjectId": "ps_afeab69a4002", "pathId": PATH,
        "stageId": STAGE, "taskId": task_id, "dayId": DAY, "globalDayIndex": 1,
    }
    base.update(params)
    query = "&".join(f"{key}={value}" for key, value in base.items())
    return f"/api/sections/{task_id}/generated-resources?{query}"


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="owner"), LearnerModel(id="other"),
            PersonalSubjectModel(id="ps_afeab69a4002", learner_id="owner", name="Course"),
            PersonalSubjectModel(id="other-subject", learner_id="other", name="Other"),
            SessionModel(id=SESSION, learner_id="owner", subject_id="ps_afeab69a4002"),
            LearningPathModel(id=PATH, session_id=SESSION, estimated_days=1, stages=[{
                "id": STAGE, "stage_id": STAGE, "days": [{
                    "id": DAY, "dayId": DAY, "day": 1, "globalDayIndex": 1,
                    "tasks": [{"id": TASK, "task_id": TASK}, {"id": "t-empty", "task_id": "t-empty"}],
                }],
            }]),
            ResourceModel(
                id="generated-t0", session_id=SESSION, type="summary_card", title="Summary", content="content",
                tags=["section_generated"], related_stage_id=STAGE, related_section_id=TASK, task_id=TASK,
            ),
        ])
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        owner, other = _headers("owner"), _headers("other")
        ready = client.get(_url(), headers=owner)
        assert ready.status_code == 200 and [item["id"] for item in ready.json()["data"]["resources"]] == ["generated-t0"]
        assert client.get(_url("t-empty"), headers=owner).status_code == 200
        assert client.get(_url(globalDayIndex=2), headers=owner).status_code == 409
        assert client.get(_url("missing"), headers=owner).status_code == 404
        assert client.get(_url(), headers=other).status_code == 403
        assert client.get(f"/api/sections/{TASK}/generated-resources?sessionId={SESSION}&subjectId=ps_afeab69a4002", headers=owner).status_code == 400
        detail = client.get("/api/resources/generated-t0", params={"sessionId": SESSION, "subjectId": "ps_afeab69a4002"}, headers=owner)
        assert detail.status_code == 200 and detail.json()["data"]["resource"]["id"] == "generated-t0"
    print("generated resources canonical scope: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        Path(_db_path).unlink(missing_ok=True)
