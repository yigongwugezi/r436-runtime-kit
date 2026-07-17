"""Learner ownership checks for assessment routes."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import AttemptModel, ExamSetModel, QuizModel, SessionModel


def require_owned_session(db: Session, session_id: str, learner_id: str) -> SessionModel:
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.learner_id == learner_id)
        .first()
    )
    if session is not None:
        return session
    # Allow anonymous→real learner transition (normal login flow)
    from app.db.repository import try_upgrade_anonymous_session
    if try_upgrade_anonymous_session(db, session_id, learner_id):
        session = (
            db.query(SessionModel)
            .filter(SessionModel.id == session_id, SessionModel.learner_id == learner_id)
            .first()
        )
        if session is not None:
            return session
    exists = db.query(SessionModel.id).filter(SessionModel.id == session_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="resource not found")
    raise HTTPException(status_code=403, detail="access denied")


def _owned(db: Session, model, resource_id: str, learner_id: str):
    resource = (
        db.query(model)
        .join(SessionModel, model.session_id == SessionModel.id)
        .filter(model.id == resource_id, SessionModel.learner_id == learner_id)
        .first()
    )
    if resource is not None:
        return resource
    # Allow anonymous→real learner transition (normal login flow)
    # Find the resource's session, upgrade it, then re-check
    raw = db.query(model).filter(model.id == resource_id).first()
    if raw is not None:
        from app.db.repository import try_upgrade_anonymous_session
        if try_upgrade_anonymous_session(db, raw.session_id, learner_id):
            resource = (
                db.query(model)
                .join(SessionModel, model.session_id == SessionModel.id)
                .filter(model.id == resource_id, SessionModel.learner_id == learner_id)
                .first()
            )
            if resource is not None:
                return resource
    exists = db.query(model.id).filter(model.id == resource_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="resource not found")
    raise HTTPException(status_code=403, detail="access denied")


def require_owned_quiz(db: Session, quiz_id: str, learner_id: str) -> QuizModel:
    return _owned(db, QuizModel, quiz_id, learner_id)


def require_owned_exam_set(db: Session, exam_set_id: str, learner_id: str) -> ExamSetModel:
    return _owned(db, ExamSetModel, exam_set_id, learner_id)


def require_owned_attempt(db: Session, attempt_id: str, learner_id: str) -> AttemptModel:
    attempt = (
        db.query(AttemptModel)
        .join(SessionModel, AttemptModel.session_id == SessionModel.id)
        .filter(AttemptModel.attempt_id == attempt_id, SessionModel.learner_id == learner_id)
        .first()
    )
    if attempt is not None:
        return attempt
    # Allow anonymous→real learner transition (normal login flow)
    raw = db.query(AttemptModel).filter(AttemptModel.attempt_id == attempt_id).first()
    if raw is not None:
        from app.db.repository import try_upgrade_anonymous_session
        if try_upgrade_anonymous_session(db, raw.session_id, learner_id):
            attempt = (
                db.query(AttemptModel)
                .join(SessionModel, AttemptModel.session_id == SessionModel.id)
                .filter(AttemptModel.attempt_id == attempt_id, SessionModel.learner_id == learner_id)
                .first()
            )
            if attempt is not None:
                return attempt
    exists = db.query(AttemptModel.attempt_id).filter(AttemptModel.attempt_id == attempt_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="resource not found")
    raise HTTPException(status_code=403, detail="access denied")


def require_parent_attempt(
    db: Session,
    attempt_id: str,
    learner_id: str,
    *,
    quiz_id: str = "",
    exam_set_id: str = "",
) -> AttemptModel:
    attempt = (
        db.query(AttemptModel)
        .join(SessionModel, AttemptModel.session_id == SessionModel.id)
        .filter(AttemptModel.attempt_id == attempt_id, SessionModel.learner_id == learner_id)
        .first()
    )
    if attempt is None:
        # Allow anonymous→real learner transition (normal login flow)
        raw = db.query(AttemptModel).filter(AttemptModel.attempt_id == attempt_id).first()
        if raw is None:
            raise HTTPException(status_code=404, detail="resource not found")
        from app.db.repository import try_upgrade_anonymous_session
        if try_upgrade_anonymous_session(db, raw.session_id, learner_id):
            attempt = (
                db.query(AttemptModel)
                .join(SessionModel, AttemptModel.session_id == SessionModel.id)
                .filter(AttemptModel.attempt_id == attempt_id, SessionModel.learner_id == learner_id)
                .first()
            )
        if attempt is None:
            raise HTTPException(status_code=403, detail="access denied")
    if (quiz_id and attempt.quiz_id != quiz_id) or (exam_set_id and attempt.exam_set_id != exam_set_id):
        raise HTTPException(status_code=403, detail="access denied")
    return attempt


def require_matching_session(owner_session_id: str, supplied_session_id: str) -> str:
    """Use the parent resource's session and reject explicit cross-session spoofing."""
    if supplied_session_id and supplied_session_id != owner_session_id:
        raise HTTPException(status_code=403, detail="access denied")
    return owner_session_id


def list_owned_quizzes(db: Session, learner_id: str, *, session_id: str = "", scope_type: str = "") -> list[QuizModel]:
    query = db.query(QuizModel).join(SessionModel, QuizModel.session_id == SessionModel.id).filter(SessionModel.learner_id == learner_id)
    if session_id:
        require_owned_session(db, session_id, learner_id)
        query = query.filter(QuizModel.session_id == session_id)
    if scope_type:
        query = query.filter(QuizModel.scope_type == scope_type)
    return query.order_by(QuizModel.created_at.desc()).all()


def list_owned_exam_sets(db: Session, learner_id: str, *, session_id: str = "", scope_type: str = "", status: str = "") -> list[ExamSetModel]:
    query = db.query(ExamSetModel).join(SessionModel, ExamSetModel.session_id == SessionModel.id).filter(SessionModel.learner_id == learner_id)
    if session_id:
        require_owned_session(db, session_id, learner_id)
        query = query.filter(ExamSetModel.session_id == session_id)
    if scope_type:
        query = query.filter(ExamSetModel.scope_type == scope_type)
    if status:
        query = query.filter(ExamSetModel.status == status)
    return query.order_by(ExamSetModel.created_at.desc()).all()
