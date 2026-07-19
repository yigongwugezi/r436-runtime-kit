"""Focused checks for subject-scoped canonical chat sessions."""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, LearnerModel, PersonalSubjectModel, SessionModel
from app.services.canonical_learning_session import ensure_canonical_learning_session


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add_all([LearnerModel(id="learner", nickname="Learner"), PersonalSubjectModel(id="ps_a", learner_id="learner", name="A"), PersonalSubjectModel(id="ps_b", learner_id="learner", name="B")])
        db.commit()
        first, created = ensure_canonical_learning_session(db, "learner", "ps_a")
        second, repeated = ensure_canonical_learning_session(db, "learner", "ps_a")
        other, _ = ensure_canonical_learning_session(db, "learner", "ps_b")
        assert created and not repeated and first["session_id"] == second["session_id"]
        assert other["session_id"] != first["session_id"]
        assert db.query(SessionModel).filter_by(learner_id="learner", subject_id="ps_a").count() == 1
    finally:
        db.close()
        engine.dispose()
    print("chat session lifecycle: PASS")


if __name__ == "__main__":
    main()
