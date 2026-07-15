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
            _subject, created = get_or_create_personal_subject(db, auth.learner_id, name, sub.get("description"))
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
    """Return the most recent session_id linked to a subject.

    For parent accounts, returns the child's session so data queries
    (profile, analytics, resources, etc.) can use the correct scope.

    Lookup strategy (most → least specific):
    1. Session linked to this exact subject (subject_id match).
    2. Session linked to this subject regardless of learner_id
       (handles sessions created before learner_id backfill).
    3. Any recent session for this learner — link it to the subject.
    4. Return None if no session exists yet.
    """
    db = SessionLocal()
    try:
        target_id = _get_target_learner_id(db, auth)

        session = None

        # 1. Ideal: subject_id + learner_id match
        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.learner_id == target_id,
                SessionModel.subject_id == subject_id,
            )
            .order_by(SessionModel.updated_at.desc())
            .first()
        )

        # 2. Subject match without learner_id (pre-backfill sessions)
        if session is None:
            session = (
                db.query(SessionModel)
                .filter(SessionModel.subject_id == subject_id)
                .order_by(SessionModel.updated_at.desc())
                .first()
            )
            # Backfill learner_id if missing
            if session is not None and not session.learner_id:
                session.learner_id = target_id
                db.commit()
                logger.info("Backfilled learner_id on session %s → %s", session.id, target_id)

        # 3. Any unbound session for this learner — link it to this subject.
        #    Only match sessions whose subject_id is NULL; sessions already
        #    bound to a different subject must not be returned (they belong
        #    to that other subject, not this one).
        if session is None:
            session = (
                db.query(SessionModel)
                .filter(
                    SessionModel.learner_id == target_id,
                    SessionModel.subject_id.is_(None),
                )
                .order_by(SessionModel.updated_at.desc())
                .first()
            )
            if session is not None:
                session.subject_id = subject_id
                db.commit()
                logger.info("Linked session %s to subject %s", session.id, subject_id)

        logger.info(
            "Session resolution: subject=%s target=%s → %s",
            subject_id, target_id, session.id if session else "NOT FOUND",
        )
        return {
            "status": "success",
            "data": {"session_id": session.id if session else None},
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
