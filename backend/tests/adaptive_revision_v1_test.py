"""Focused executable check for the explainable failed-quiz revision v1."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
fd, db_path = tempfile.mkstemp(prefix="edu-adaptive-revision-", suffix=".db"); os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.engine import SessionLocal, engine
from app.db.models import AnswerRecordModel, AttemptModel, Base, LearnerModel, LearningEventModel, LearningPathModel, PracticeQuestionModel, SessionModel
from app.services.adaptive_revision import create_failed_quiz_revision
from app.services.conversation_state import conversation_store


def main() -> None:
    Base.metadata.create_all(engine); conversation_store._sessions.clear(); conversation_store.enable_db()
    db = SessionLocal()
    try:
        db.add_all([
            LearnerModel(id="learner"), SessionModel(id="session", learner_id="learner", subject_id="subject"),
            LearningPathModel(id="path", session_id="session", subject_id="subject", stages=[{"id": "stage", "days": [{"id": "day", "tasks": [{"id": "quiz", "type": "quiz", "title": "Original quiz", "status": "completed", "mastery": 100}]}]}]),
            PracticeQuestionModel(question_id="question", question_set_id="quiz-set", session_id="session", stem="x", knowledge_points=["recursion"]),
            AttemptModel(attempt_id="attempt-low", session_id="session", subject_id="subject", path_id="path", stage_id="stage", task_id="quiz", quiz_id="quiz-set", learner_id="learner", idempotency_key="submit-low", attempt_number=1, total_score=20, status="graded"),
            AttemptModel(attempt_id="attempt-pass", session_id="session", subject_id="subject", path_id="path", stage_id="stage", task_id="quiz", quiz_id="quiz-set", learner_id="learner", idempotency_key="submit-pass", attempt_number=2, total_score=100, status="graded"),
            AnswerRecordModel(session_id="session", attempt_id="attempt-low", question_id="question", student_answer="wrong", total_score=0),
            LearningEventModel(event_id="evt-low", session_id="session", learner_id="learner", subject_id="subject", event_type="quiz_result", attempt_id="attempt-low"),
        ]); db.commit()
        low = db.query(AttemptModel).filter_by(attempt_id="attempt-low").one()
        revision = create_failed_quiz_revision(db, low); assert revision and revision["idempotency_key"].endswith("adaptive_review_v1")
        assert revision["explainability"]["evidence"]["weakKPs"] == ["recursion"]
        assert len(revision["explainability"]["addedTasks"]) == 1
        assert {item["stage"] for item in revision["workflow_trace"]} >= {"QUIZ_ATTEMPT_RECORDED", "REVISION_PENDING"}
        assert create_failed_quiz_revision(db, low)["revision_id"] == revision["revision_id"]
        assert create_failed_quiz_revision(db, db.query(AttemptModel).filter_by(attempt_id="attempt-pass").one()) is None
        assert conversation_store.apply_pending_revision("session")
        db.expire_all(); path = db.get(LearningPathModel, "path")
        tasks = path.stages[0]["days"][0]["tasks"]
        assert tasks[0]["status"] == "completed" and len(tasks) == 2 and tasks[1]["adaptiveRevision"]
    finally:
        db.close(); engine.dispose(); Path(db_path).unlink(missing_ok=True)
    print("adaptive revision v1: PASS")


if __name__ == "__main__": main()
