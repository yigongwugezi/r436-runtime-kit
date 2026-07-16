"""Canonical personal-subject identity and safe duplicate inspection."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
import unicodedata
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    LearningEventModel,
    LearningPathModel,
    PersonalSubjectModel,
    ProfileSnapshotModel,
    ResourceModel,
    SessionModel,
    TextbookModel,
)


# ponytail: process-wide lock protects legacy SQLite files; use a database migration
# before scaling subject creation across multiple application processes.
_CREATE_LOCK = Lock()
_TRAILING_SEPARATOR = "、，。,:;；："


def canonical_subject_name(value: str) -> str:
    """Normalize presentation-only differences without altering a topic itself."""
    name = " ".join(unicodedata.normalize("NFKC", str(value or "")).split())
    return name.rstrip(_TRAILING_SEPARATOR).strip()


def get_or_create_personal_subject(
    db: Session, learner_id: str, name: str, description: str | None = None,
) -> tuple[PersonalSubjectModel, bool]:
    """Return one learner-scoped subject, serializing legacy SQLite writes too."""
    canonical_name = canonical_subject_name(name)
    if not canonical_name:
        raise ValueError("subject name is required")

    with _CREATE_LOCK:
        rows = (
            db.query(PersonalSubjectModel)
            .filter(PersonalSubjectModel.learner_id == learner_id)
            .order_by(PersonalSubjectModel.created_at.asc(), PersonalSubjectModel.id.asc())
            .all()
        )
        existing = next((row for row in rows if canonical_subject_name(row.name) == canonical_name), None)
        if existing is not None:
            return existing, False

        subject = PersonalSubjectModel(
            id=f"ps_{uuid.uuid4().hex[:12]}", learner_id=learner_id,
            name=canonical_name, description=description,
        )
        db.add(subject)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(PersonalSubjectModel)
                .filter(
                    PersonalSubjectModel.learner_id == learner_id,
                    PersonalSubjectModel.name == canonical_name,
                )
                .first()
            )
            if existing is None:
                raise
            return existing, False
        db.refresh(subject)
        return subject, True


def bind_explicit_subject_to_session(
    db: Session, session_id: str, learner_id: str, name: str,
) -> PersonalSubjectModel | None:
    """Bind an unscoped session to a learner subject named in this message."""
    canonical_name = canonical_subject_name(name)
    if not session_id or not learner_id or not canonical_name:
        return None

    session = db.get(SessionModel, session_id)
    if session is None or session.learner_id != learner_id or session.subject_id:
        return None

    subject, _ = get_or_create_personal_subject(db, learner_id, canonical_name)
    updated = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.learner_id == learner_id,
            SessionModel.subject_id.is_(None),
        )
        .update({SessionModel.subject_id: subject.id}, synchronize_session=False)
    )
    if not updated:
        db.rollback()
        return None
    db.commit()
    return subject


def subject_deduplication_dry_run(db: Session, learner_id: str | None = None) -> list[dict[str, object]]:
    """Report reversible merge candidates only; this function never writes data."""
    query = db.query(PersonalSubjectModel)
    if learner_id:
        query = query.filter(PersonalSubjectModel.learner_id == learner_id)
    groups: dict[tuple[str, str], list[PersonalSubjectModel]] = defaultdict(list)
    for subject in query.order_by(PersonalSubjectModel.created_at.asc(), PersonalSubjectModel.id.asc()).all():
        groups[(subject.learner_id, canonical_subject_name(subject.name))].append(subject)

    report: list[dict[str, object]] = []
    for (owner_id, canonical_name), subjects in groups.items():
        if len(subjects) < 2:
            continue
        canonical = next((subject for subject in subjects if subject.name == canonical_name), subjects[0])
        duplicates = [subject for subject in subjects if subject.id != canonical.id]
        subject_ids = [subject.id for subject in subjects]
        linked_sessions = db.query(SessionModel.id, SessionModel.subject_id).filter(SessionModel.subject_id.in_(subject_ids)).all()
        session_ids = [row[0] for row in linked_sessions]
        impact = {
            "sessions": len(session_ids),
            "profiles": db.query(ProfileSnapshotModel).filter(ProfileSnapshotModel.session_id.in_(session_ids)).count() if session_ids else 0,
            "paths": db.query(LearningPathModel).filter(LearningPathModel.session_id.in_(session_ids)).count() if session_ids else 0,
            "resources": db.query(ResourceModel).filter(ResourceModel.session_id.in_(session_ids)).count() if session_ids else 0,
            "events": db.query(LearningEventModel).filter(LearningEventModel.session_id.in_(session_ids)).count() if session_ids else 0,
            "textbooks": db.query(TextbookModel).filter(TextbookModel.subject_id.in_(subject_ids)).count(),
        }
        report.append({
            "learner_id": owner_id,
            "canonical_name": canonical_name,
            "canonical_subject_id": canonical.id,
            "duplicate_subject_ids": [subject.id for subject in duplicates],
            "impact": impact,
            "manual_review_required": impact["textbooks"] > 1,
            "session_reassignments": [
                {"session_id": session_id, "from_subject_id": subject_id, "to_subject_id": canonical.id}
                for session_id, subject_id in linked_sessions if subject_id != canonical.id
            ],
            "rollback_session_reassignments": [
                {"session_id": session_id, "from_subject_id": canonical.id, "to_subject_id": subject_id}
                for session_id, subject_id in linked_sessions if subject_id != canonical.id
            ],
            "retained_session_scoped_data": ("profiles", "paths", "resources", "events", "workflow_tasks", "feedback", "search_history"),
            "dry_run": True,
        })
    return report
