"""Persistent AI assessment snapshot smoke test (SQLite, no provider)."""
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import Base, LearningAssessmentSnapshotModel


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        snapshot = LearningAssessmentSnapshotModel(learner_id="a", subject_id="math", session_id="s", metrics_version="v1", content={"summary": "ok"})
        db.add(snapshot)
        db.commit()
        assert db.query(LearningAssessmentSnapshotModel).filter_by(session_id="s", status="ready").one().content["summary"] == "ok"
    finally:
        db.close(); engine.dispose()
    print("learning analytics assessment: PASS")


if __name__ == "__main__":
    main()
