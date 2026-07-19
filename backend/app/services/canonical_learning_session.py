"""Resolve the one learning-data session a subject should use by default."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import LearningPathModel, PersonalSubjectModel, SessionModel
from app.db.repository import get_or_create_session


def _timestamp(value: datetime | None) -> float:
    return value.timestamp() if value else 0.0


def _formal_path(path: LearningPathModel) -> bool:
    """Planning drafts live elsewhere; a path with stages is executable."""
    return isinstance(path.stages, list) and bool(path.stages)


def resolve_canonical_learning_session(
    db: Session, learner_id: str, subject_id: str,
) -> dict[str, Any] | None:
    """Return the deterministic default learning session for one owned subject."""
    sessions = (
        db.query(SessionModel)
        .filter(
            SessionModel.subject_id == subject_id,
            (SessionModel.learner_id == learner_id) | SessionModel.learner_id.is_(None),
        )
        .all()
    )
    if not sessions:
        return None

    session_ids = [session.id for session in sessions]
    paths = [
        path for path in db.query(LearningPathModel)
        .filter(LearningPathModel.session_id.in_(session_ids))
        .all()
        if _formal_path(path)
    ]
    if paths:
        # A normal chat may update Session.updated_at but must not replace a path.
        path = sorted(
            paths,
            key=lambda item: (-_timestamp(item.updated_at), -_timestamp(item.created_at), item.id),
        )[0]
        return {
            "session_id": path.session_id,
            "subject_id": subject_id,
            "path_id": path.id,
            "source": "formal_learning_path",
            "resolved_at": datetime.utcnow().isoformat(),
        }

    session = sorted(
        sessions,
        key=lambda item: (-_timestamp(item.updated_at), -_timestamp(item.created_at), item.id),
    )[0]
    return {
        "session_id": session.id,
        "subject_id": subject_id,
        "path_id": None,
        "source": "subject_chat_session",
        "resolved_at": datetime.utcnow().isoformat(),
    }


def ensure_canonical_learning_session(
    db: Session, learner_id: str, subject_id: str,
) -> tuple[dict[str, Any], bool]:
    """Create the one initial chat session for an owned subject, if needed."""
    subject = db.get(PersonalSubjectModel, subject_id)
    if subject is None or subject.learner_id != learner_id:
        raise PermissionError("subject is outside learner scope")
    resolved = resolve_canonical_learning_session(db, learner_id, subject_id)
    if resolved:
        return resolved, False
    session_id = f"session_{subject_id}"
    get_or_create_session(
        db, session_id, learner_id=learner_id, subject_id=subject_id, require_learner=True,
    )
    resolved = resolve_canonical_learning_session(db, learner_id, subject_id)
    if resolved is None:
        raise RuntimeError("canonical session creation failed")
    return resolved, True
