"""Ownership checks shared by every student-question route."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import PracticeQuestionModel, SessionModel
from app.middleware.auth import AuthContext, validate_anonymous_learner_id


def resolve_question_learner(auth: AuthContext, supplied_learner_id: str = "") -> str:
    """Return the authenticated learner, or the existing opaque anonymous identity."""
    supplied = str(supplied_learner_id or "").strip()
    if auth.is_authenticated:
        if supplied and supplied != auth.learner_id:
            raise HTTPException(status_code=403, detail="learnerId does not match the authenticated user")
        return auth.learner_id
    learner_id = validate_anonymous_learner_id(supplied)
    if learner_id:
        return learner_id
    raise HTTPException(status_code=401, detail="authentication required")


def require_owned_session(db: Session, session_id: str, learner_id: str) -> SessionModel:
    """Resolve a session only when it belongs to the current learner."""
    owned = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.learner_id == learner_id)
        .first()
    )
    if owned is not None:
        return owned
    # Allow anonymous→real learner transition (normal login flow)
    from app.db.repository import try_upgrade_anonymous_session
    if try_upgrade_anonymous_session(db, session_id, learner_id):
        owned = (
            db.query(SessionModel)
            .filter(SessionModel.id == session_id, SessionModel.learner_id == learner_id)
            .first()
        )
        if owned is not None:
            return owned
    exists = db.query(SessionModel.id).filter(SessionModel.id == session_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="resource not found")
    raise HTTPException(status_code=403, detail="access denied")


def resolve_owned_practice_question(
    db: Session,
    question_id: str,
    learner_id: str,
    *,
    session_id: str,
) -> PracticeQuestionModel:
    """Resolve a practice question through its owner-scoped session."""
    require_owned_session(db, session_id, learner_id)
    question = (
        db.query(PracticeQuestionModel)
        .filter(
            PracticeQuestionModel.question_id == question_id,
            PracticeQuestionModel.session_id == session_id,
        )
        .first()
    )
    if question is not None:
        return question
    exists = db.query(PracticeQuestionModel.id).filter(
        PracticeQuestionModel.question_id == question_id
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="resource not found")
    raise HTTPException(status_code=403, detail="access denied")
