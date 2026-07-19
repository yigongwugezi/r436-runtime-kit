"""Personal subject routes — student creates subjects for self-directed learning.

Stored server-side so subjects are visible across browsers and to bound
parent accounts.  Differs from class_subjects.py (teacher-managed classrooms).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import (
    AnswerRecordModel,
    LearnerModel,
    PersonalSubjectModel,
    PracticeQuestionModel,
    SessionModel,
)
from app.middleware.auth import AuthContext, reject_parent, require_auth
from app.services.canonical_learning_session import resolve_canonical_learning_session
from app.services.subject_identity import canonical_subject_name, get_or_create_personal_subject

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subjects"])


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _get_target_learner_id(db, auth: AuthContext) -> str:
    """Return the learner_id whose subjects should be queried.

    For parents: returns the first bound child's ID so they can view (but
    not modify) their child's subjects.  For all other roles, returns the
    caller's own ID.
    """
    if auth.is_parent and auth.learner:
        children = (
            db.query(LearnerModel)
            .filter(LearnerModel.parent_id == auth.learner_id)
            .all()
        )
        if children:
            return children[0].id
    return auth.learner_id


def _subject_dict(ps: PersonalSubjectModel) -> dict:
    """Serialize a PersonalSubjectModel.

    Timestamps are returned as epoch milliseconds to match the frontend
    Subject type (createdAt / updatedAt: number).
    """
    return {
        "id": ps.id,
        "name": ps.name,
        "description": ps.description,
        "textbook_id": ps.textbook_id,
        "created_at": int(ps.created_at.timestamp() * 1000) if ps.created_at else 0,
        "updated_at": int(ps.updated_at.timestamp() * 1000) if ps.updated_at else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════


class CreateSubjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None


class MigrateSubjectsRequest(BaseModel):
    subjects: list[dict] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# 1. List personal subjects
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/subjects")
def list_subjects(auth: AuthContext = Depends(require_auth)) -> dict:
    """List personal subjects for the authenticated learner.

    Parent accounts receive their first bound child's subjects.
    """
    db = SessionLocal()
    try:
        target_id = _get_target_learner_id(db, auth)
        rows = (
            db.query(PersonalSubjectModel)
            .filter(PersonalSubjectModel.learner_id == target_id)
            .order_by(PersonalSubjectModel.created_at.desc())
            .all()
        )
        return {
            "status": "success",
            "data": {"subjects": [_subject_dict(r) for r in rows]},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Create a personal subject
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/subjects")
def create_subject(
    body: CreateSubjectRequest,
    auth: AuthContext = Depends(reject_parent),
) -> dict:
    """Create a new personal subject. Parents are blocked (403)."""
    name = canonical_subject_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="科目名称不能为空")

    db = SessionLocal()
    try:
        ps, _created = get_or_create_personal_subject(db, auth.learner_id, name, body.description)
        return {"status": "success", "data": {"subject": _subject_dict(ps)}}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Migrate subjects from localStorage
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/subjects/migrate")
def migrate_subjects(
    body: MigrateSubjectsRequest,
    auth: AuthContext = Depends(reject_parent),
) -> dict:
    """Bulk-import subjects from localStorage (first cross-browser login).

    Deduplicates by name against existing subjects for this learner.
    Returns the complete merged list after import.
    """
    if not body.subjects:
        # Nothing to migrate — just return current list
        db0 = SessionLocal()
        try:
            rows = (
                db0.query(PersonalSubjectModel)
                .filter(PersonalSubjectModel.learner_id == auth.learner_id)
                .order_by(PersonalSubjectModel.created_at.desc())
                .all()
            )
            return {
                "status": "success",
                "data": {"subjects": [_subject_dict(r) for r in rows]},
            }
        finally:
            db0.close()

    db = SessionLocal()
    try:
        created_count = 0
        for sub in body.subjects:
            name = canonical_subject_name(sub.get("name") or "")
            if not name:
                continue
            _subject, created = get_or_create_personal_subject(
                db,
                auth.learner_id,
                name,
                sub.get("description"),
                legacy_subject_id=sub.get("id"),
            )
            created_count += int(created)

        # Return the complete merged list
        rows = (
            db.query(PersonalSubjectModel)
            .filter(PersonalSubjectModel.learner_id == auth.learner_id)
            .order_by(PersonalSubjectModel.created_at.desc())
            .all()
        )
        logger.info(
            "Migrated %d subjects for learner %s (total now: %d)",
            created_count,
            auth.learner_id,
            len(rows),
        )
        return {
            "status": "success",
            "data": {"subjects": [_subject_dict(r) for r in rows]},
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Resolve session for a subject (parent-aware)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/subjects/session")
def get_subject_session(
    subject_id: str = Query(..., alias="subject_id"),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Return the canonical learning session linked to a subject.

    For parent accounts, returns the child's session so data queries
    (profile, analytics, resources, etc.) can use the correct scope.

    The subject must belong to the target learner.  For historical sessions
    without ``learner_id``, the owned personal subject is the required proof
    of ownership; this endpoint never backfills or rebinds old records.
    """
    db = SessionLocal()
    try:
        target_id = _get_target_learner_id(db, auth)
        subject = db.get(PersonalSubjectModel, subject_id)
        if subject is None or subject.learner_id != target_id:
            return {"status": "success", "data": {"session_id": None}}

        resolved = resolve_canonical_learning_session(db, target_id, subject_id)

        logger.info(
            "Session resolution: subject=%s target=%s → %s",
            subject_id, target_id, resolved["session_id"] if resolved else "NOT FOUND",
        )
        return {
            "status": "success",
            "data": resolved or {
                "session_id": None,
                "subject_id": subject_id,
                "path_id": None,
                "source": None,
                "resolved_at": None,
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Delete a personal subject  (must be LAST — path param {subject_id})
# ═══════════════════════════════════════════════════════════════════════════


@router.delete("/subjects/{subject_id}")
def delete_subject(
    subject_id: str,
    auth: AuthContext = Depends(reject_parent),
) -> dict:
    """Delete a personal subject and all linked session data. Only the owner may delete it."""
    db = SessionLocal()
    try:
        ps = db.get(PersonalSubjectModel, subject_id)
        if ps is None:
            raise HTTPException(status_code=404, detail="科目不存在")
        if ps.learner_id != auth.learner_id:
            raise HTTPException(status_code=403, detail="无权删除此科目")

        # ── Clean up linked textbook files from server disk ──────────
        # Only delete the server-side cached/processed copies.
        # The student's original local PDF is never touched.
        if ps.textbook_id:
            from app.db.models import TextbookModel, TextbookPageContentModel
            from app.services.textbook_processor import delete_textbook_files

            tb = db.get(TextbookModel, ps.textbook_id)
            if tb is not None:
                # Remove per-page extracted content
                db.query(TextbookPageContentModel).filter(
                    TextbookPageContentModel.textbook_id == tb.id
                ).delete()
                # Remove textbook DB record
                db.delete(tb)
                db.flush()
                # Remove server-side cached/processed files (PDF copy, rendered pages)
                delete_textbook_files(tb.id)
                logger.info(
                    "Cleaned up textbook %s files for subject %s",
                    tb.id, subject_id,
                )

        # Clean up linked sessions so old data doesn't leak if the subject
        # is re-created.  SessionModel cascades messages, profile snapshots,
        # learning paths, resources, events, and daily tasks automatically.
        # PracticeQuestionModel and AnswerRecordModel use plain-string
        # session_id (no FK), so they must be deleted explicitly.
        linked_sessions = (
            db.query(SessionModel)
            .filter(SessionModel.subject_id == subject_id)
            .all()
        )
        for s in linked_sessions:
            db.query(PracticeQuestionModel).filter(
                PracticeQuestionModel.session_id == s.id
            ).delete()
            db.query(AnswerRecordModel).filter(
                AnswerRecordModel.session_id == s.id
            ).delete()
            db.delete(s)

        db.delete(ps)
        db.commit()
        logger.info(
            "Deleted subject %s and %d linked sessions for learner %s",
            subject_id, len(linked_sessions), auth.learner_id,
        )
        return {"status": "success", "data": {}}
    finally:
        db.close()
