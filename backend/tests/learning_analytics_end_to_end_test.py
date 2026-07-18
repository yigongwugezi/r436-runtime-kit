"""Deterministic, network-free learning analytics journey."""
from __future__ import annotations
import os, sys, tempfile, types
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
os.environ["JWT_SECRET"] = "analytics-e2e"
_fd, _path = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ahocorasick", types.SimpleNamespace(Automaton=type("A", (), {"add_word": lambda *_: None, "make_automaton": lambda *_: None, "iter": lambda *_: ()})))

from fastapi.testclient import TestClient
from app.db.engine import SessionLocal, engine
from app.db.models import AnswerRecordModel, AttemptModel, Base, LearnerModel, LearningEventModel, LearningPathModel, PersonalSubjectModel, SessionModel
from app.main import app
from app.services import llm_assessment
from app.utils.auth import create_token

def headers(learner: str): return {"Authorization": f"Bearer {create_token(learner, 'student')}"}

def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="a"), LearnerModel(id="b"), PersonalSubjectModel(id="math", learner_id="a", name="Math"),
            SessionModel(id="s", learner_id="a", subject_id="math"),
            LearningPathModel(id="p", session_id="s", stages=[{"id":"one","tasks":[{"id":"lecture","type":"lecture"}]},{"id":"two","tasks":[{"id":"quiz","type":"quiz"}]}]),
            AttemptModel(attempt_id="attempt", session_id="s", subject_id="math", learner_id="a", status="graded", total_score=1, max_score=1),
            AnswerRecordModel(session_id="s", attempt_id="attempt", question_id="q", student_answer="A", total_score=1),
            LearningEventModel(session_id="s", learner_id="a", subject_id="math", event_type="quiz_result", attempt_id="attempt", metadata_={"total": 1, "correct": 1}),
        ]); db.commit()
    finally: db.close()
    original = llm_assessment.run_llm_assessment
    llm_assessment.run_llm_assessment = lambda **_: {"status":"ready", "summary":"fake", "scores":{"knowledge_mastery":80}}
    try:
        with TestClient(app) as client:
            assert client.get("/api/learning-analytics?sessionId=s&subjectId=math").status_code == 401
            assert client.get("/api/learning-analytics?sessionId=s&subjectId=math", headers=headers("b")).status_code == 403
            before = client.get("/api/learning-analytics?sessionId=s&subjectId=math", headers=headers("a")).json()["data"]
            assert before["pathProgress"]["nextTask"]["taskId"] == "lecture" and before["assessmentCount"] == 1
            assessment = client.post("/api/learning-assessment/generate?sessionId=s&subjectId=math", headers=headers("a"))
            assert assessment.status_code == 200 and assessment.json()["data"]["summary"] == "fake"
            cached = client.post("/api/learning-assessment/generate?sessionId=s&subjectId=math", headers=headers("a")).json()["data"]
            assert cached["cached"] is True
    finally:
        llm_assessment.run_llm_assessment = original
        engine.dispose(); Path(_path).unlink(missing_ok=True)
    print("learning analytics end to end: PASS")

if __name__ == "__main__": main()
