"""Attempt-backed learning analytics metrics regression checks."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import AnswerRecordModel, AttemptModel, Base, LearningEventModel
from app.db.repository import get_assessment_metrics, get_event_analytics


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        now = datetime.now(timezone.utc)
        db.add_all([
            AttemptModel(attempt_id="a1", session_id="s", subject_id="math", status="graded", total_score=50, max_score=100, submitted_at=now),
            AttemptModel(attempt_id="a2", session_id="s", subject_id="math", status="completed", total_score=100, max_score=100, submitted_at=now + timedelta(minutes=1)),
            AttemptModel(attempt_id="draft", session_id="s", subject_id="math", status="started", total_score=100, max_score=100),
            AnswerRecordModel(session_id="s", attempt_id="a1", question_id="q1", student_answer="A", total_score=1),
            AnswerRecordModel(session_id="s", attempt_id="a1", question_id="q2", student_answer="B", total_score=0),
            AnswerRecordModel(session_id="s", attempt_id="a2", question_id="q3", student_answer="C", total_score=1),
            LearningEventModel(session_id="s", subject_id="math", event_type="quiz_result", attempt_id="a1", metadata_={"total": 99, "correct": 99}, created_at=now),
            LearningEventModel(session_id="s", subject_id="math", event_type="quiz_result", metadata_={"total": 2, "correct": 1, "normalizedScore": .5}, created_at=now + timedelta(minutes=2)),
        ])
        db.commit()
        events = db.query(LearningEventModel).all()
        metrics = get_assessment_metrics(db, "s", "math", events)
        assert metrics["assessmentCount"] == 3  # two attempts plus one legacy event
        assert metrics["questionAnsweredCount"] == 5 and metrics["correctQuestionCount"] == 3
        assert metrics["quizAccuracy"] == 60
        assert metrics["latestQuizScore"]["accuracy"] == 50 and metrics["bestQuizScore"]["accuracy"] == 100
        assert metrics["metricDetails"]["accuracy"]["status"] == "available"
        analytics = get_event_analytics(db, "s", subject_id="math")
        assert analytics["practiceCount"] == 3 and analytics["trackedStudyDuration"] == 0
        assert analytics["regularityScore"] is None and analytics["regularityMetric"]["status"] == "insufficient_data"
    finally:
        db.close()
        engine.dispose()
    print("learning analytics metrics: PASS")


if __name__ == "__main__":
    main()
