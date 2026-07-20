"""Focused checks for subject-scoped canonical chat sessions."""

import sys
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.db.models import Base, LearnerModel, LearningPathModel, PersonalSubjectModel, SessionModel, TextbookModel
from app.middleware.auth import AuthContext
from app.routers import chat_router, product
from app.services.canonical_learning_session import ensure_canonical_learning_session, resolve_canonical_learning_session


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        db.add_all([LearnerModel(id="learner", nickname="Learner"), PersonalSubjectModel(id="ps_a", learner_id="learner", name="A"), PersonalSubjectModel(id="ps_b", learner_id="learner", name="B")])
        db.commit()
        first, created = ensure_canonical_learning_session(db, "learner", "ps_a")
        second, repeated = ensure_canonical_learning_session(db, "learner", "ps_a")
        other, _ = ensure_canonical_learning_session(db, "learner", "ps_b")
        assert created and not repeated and first["session_id"] == second["session_id"]
        assert other["session_id"] != first["session_id"]
        assert db.query(SessionModel).filter_by(learner_id="learner", subject_id="ps_a").count() == 1

        empty_subject = PersonalSubjectModel(id="ps_empty", learner_id="learner", name="")
        db.add(empty_subject)
        db.commit()
        db.add(TextbookModel(id="tb_empty", subject_id="ps_empty", learner_id="learner", status="ready", chapters_json=[]))
        empty_subject.textbook_id = "tb_empty"
        db.add(SessionModel(id="session_empty", learner_id="learner", subject_id="ps_empty"))
        db.commit()
        state = {"chat_mode": "planning"}
        with patch("app.db.engine.SessionLocal", factory):
            chat_router._inject_textbook_context(state, "session_empty")
        assert state["course_id"] == "ps_empty"

        db.add(SessionModel(id="session_archive", learner_id="learner", subject_id="ps_b"))
        db.commit()
        with patch.object(product, "SessionLocal", factory):
            archived = product.delete_chat_session("session_archive", auth=AuthContext(learner_id="learner"))
        db.expire_all()
        assert archived["data"]["archived"] is True
        assert db.get(SessionModel, "session_archive").status == "archived"
        assert resolve_canonical_learning_session(db, "learner", "ps_b")["session_id"] == other["session_id"]

        db.add(LearningPathModel(id="formal_path", session_id=first["session_id"], subject_id="ps_a", stages=[{"id": "stage"}]))
        db.commit()
        with patch.object(product, "SessionLocal", factory):
            try:
                product.delete_chat_session(first["session_id"], auth=AuthContext(learner_id="learner"))
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("formal learning sessions must not be archived")
        db.expire_all()
        assert db.get(SessionModel, first["session_id"]).status == "active"
        assert db.get(LearningPathModel, "formal_path") is not None
    finally:
        db.close()
        engine.dispose()
    print("chat session lifecycle: PASS")


if __name__ == "__main__":
    main()
