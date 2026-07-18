"""Authorization and subject-scope checks for learning analytics."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
_handle, _db_path = tempfile.mkstemp(prefix="edu-analytics-auth-", suffix=".db")
os.close(_handle)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "analytics-auth-test-secret"

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal, engine
from app.db.models import Base, LearnerModel, LearningEventModel, LearningPathModel, PersonalSubjectModel, SessionModel
from app.main import app
from app.services import llm_assessment
from app.utils.auth import create_token


def _headers(learner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(learner_id, 'student')}"}


def _seed() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="learner-a"), LearnerModel(id="learner-b"),
            PersonalSubjectModel(id="math", learner_id="learner-a", name="Math"),
            PersonalSubjectModel(id="physics", learner_id="learner-a", name="Physics"),
            PersonalSubjectModel(id="other", learner_id="learner-b", name="Other"),
            SessionModel(id="math-session", learner_id="learner-a", subject_id="math"),
            SessionModel(id="other-session", learner_id="learner-b", subject_id="other"),
            SessionModel(id="multi-session", learner_id="learner-a"),
            SessionModel(id="legacy-session", subject_id="math"),
            SessionModel(id="orphan-session", subject_id="orphan"),
            LearningPathModel(id="math-path", session_id="math-session", stages=[{"id": "math-stage"}]),
            LearningEventModel(session_id="math-session", learner_id="learner-a", subject_id="math", event_type="resource_view", metadata_={"subjectId": "math"}),
            LearningEventModel(session_id="multi-session", learner_id="learner-a", subject_id="math", event_type="resource_view", metadata_={"subjectId": "math"}),
            LearningEventModel(session_id="multi-session", learner_id="learner-a", subject_id="physics", event_type="resource_complete", metadata_={"subjectId": "physics"}),
        ])
        db.commit()
    finally:
        db.close()


def main() -> None:
    _seed()
    calls = {"provider": 0}
    original = llm_assessment.run_llm_assessment
    llm_assessment.run_llm_assessment = lambda **_kwargs: calls.__setitem__("provider", calls["provider"] + 1) or {"status": "ok"}
    try:
        with TestClient(app) as client:
            owner, other = _headers("learner-a"), _headers("learner-b")
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math").status_code == 401
            assert client.post("/api/learning-assessment/generate?sessionId=math-session&subjectId=math").status_code == 401
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math", headers=owner).status_code == 200
            assert client.get("/api/learning-analytics?sessionId=other-session&subjectId=other", headers=owner).status_code == 403
            assert client.post("/api/learning-assessment/generate?sessionId=other-session&subjectId=other", headers=owner).status_code == 403
            assert calls["provider"] == 0
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math&learnerId=learner-b", headers=owner).status_code == 200
            assert client.get("/api/learning-analytics?sessionId=multi-session", headers=owner).status_code == 400
            math = client.get("/api/learning-analytics?sessionId=multi-session&subjectId=math", headers=owner).json()["data"]
            assert math["eventBreakdown"] == {"resource_view": 1}
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math&pathId=bad", headers=owner).status_code == 403
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math&pathId=math-path&stageId=bad", headers=owner).status_code == 403
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math&pathId=math-path&stageId=math-stage", headers=owner).status_code == 200
            assert client.get("/api/learning-analytics?sessionId=legacy-session&subjectId=math", headers=owner).status_code == 200
            assert client.get("/api/learning-analytics?sessionId=orphan-session&subjectId=orphan", headers=owner).status_code == 403
            assert client.post("/api/learning-assessment/generate?sessionId=math-session&subjectId=math", headers=owner).status_code == 200
            assert calls["provider"] == 1
            assert client.get("/api/learning-analytics?sessionId=math-session&subjectId=math", headers=other).status_code == 403
    finally:
        llm_assessment.run_llm_assessment = original
    print("learning analytics authorization: PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        try:
            Path(_db_path).unlink(missing_ok=True)
        except PermissionError:
            pass
