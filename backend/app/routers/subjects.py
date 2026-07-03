"""Personal subject routes — student creates subjects for self-directed learning.

Stored server-side so subjects are visible across browsers and to bound
parent accounts.  Differs from class_subjects.py (teacher-managed classrooms).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import SessionLocal
from app.db.models import LearnerModel, PersonalSubjectModel, SessionModel
from app.middleware.auth import AuthContext, reject_parent, require_auth

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
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="科目名称不能为空")

    db = SessionLocal()
    try:
        ps = PersonalSubjectModel(
            id=f"ps_{uuid.uuid4().hex[:12]}",
            learner_id=auth.learner_id,
            name=name,
            description=body.description,
        )
        db.add(ps)
        db.commit()
        db.refresh(ps)
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
        # Collect existing names for this learner
        existing = (
            db.query(PersonalSubjectModel)
            .filter(PersonalSubjectModel.learner_id == auth.learner_id)
            .all()
        )
        existing_names = {ps.name for ps in existing}

        created_count = 0
        for sub in body.subjects:
            name = (sub.get("name") or "").strip()
            if not name or name in existing_names:
                continue
            ps = PersonalSubjectModel(
                id=f"ps_{uuid.uuid4().hex[:12]}",
                learner_id=auth.learner_id,
                name=name,
                description=sub.get("description"),
            )
            db.add(ps)
            existing_names.add(name)
            created_count += 1

        if created_count > 0:
            db.commit()

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

        # 3. Any session for this learner — link it to this subject
        if session is None:
            session = (
                db.query(SessionModel)
                .filter(SessionModel.learner_id == target_id)
                .order_by(SessionModel.updated_at.desc())
                .first()
            )
            if session is not None and not session.subject_id:
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
    """Delete a personal subject. Only the owner may delete it."""
    db = SessionLocal()
    try:
        ps = db.get(PersonalSubjectModel, subject_id)
        if ps is None:
            raise HTTPException(status_code=404, detail="科目不存在")
        if ps.learner_id != auth.learner_id:
            raise HTTPException(status_code=403, detail="无权删除此科目")

        db.delete(ps)
        db.commit()
        return {"status": "success", "data": {}}
    finally:
        db.close()
