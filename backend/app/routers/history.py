"""Learning history routes — time/subject-filtered event and activity queries."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func

from app.db.engine import SessionLocal
from app.db.models import DailyTaskModel, LearningEventModel, MessageModel, ResourceModel
from app.middleware.auth import AuthContext, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["history"])


# ═══════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/learner/me/history")
def get_learning_history(
    auth: AuthContext = Depends(require_auth),
    start_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    subject_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Get the current learner's learning history with optional filters."""
    db = SessionLocal()
    try:
        learner_id = auth.learner_id

        # Parse date range
        start = _parse_date(start_date) or (datetime.now(timezone.utc) - timedelta(days=30))
        end = _parse_date(end_date) or datetime.now(timezone.utc)

        # Base query — events for this learner's sessions
        base = db.query(LearningEventModel).filter(
            LearningEventModel.session.has(learner_id=learner_id),
            LearningEventModel.created_at >= start,
            LearningEventModel.created_at <= end,
        )
        if subject_id:
            base = base.filter(
                LearningEventModel.session.has(subject_id=subject_id)
            )

        total = base.count()
        events = (
            base.order_by(desc(LearningEventModel.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Aggregate stats
        total_study_minutes = (
            db.query(func.coalesce(func.sum(
                func.json_extract(LearningEventModel.metadata_, "$.duration")
            ), 0))
            .filter(
                LearningEventModel.session.has(learner_id=learner_id),
                LearningEventModel.created_at >= start,
                LearningEventModel.created_at <= end,
            )
            .scalar()
        ) or 0

        completed_tasks = (
            db.query(func.count(DailyTaskModel.id))
            .filter(
                DailyTaskModel.session.has(learner_id=learner_id),
                DailyTaskModel.completed == True,
                DailyTaskModel.completed_at >= start,
                DailyTaskModel.completed_at <= end,
            )
            .scalar()
        ) or 0

        completed_resources = (
            db.query(func.count(ResourceModel.id))
            .filter(
                ResourceModel.session.has(learner_id=learner_id),
                ResourceModel.study_status == "completed",
                ResourceModel.updated_at >= start,
                ResourceModel.updated_at <= end,
            )
            .scalar()
        ) or 0

        message_count = (
            db.query(func.count(MessageModel.id))
            .filter(
                MessageModel.session.has(learner_id=learner_id),
                MessageModel.role == "user",
                MessageModel.created_at >= start,
                MessageModel.created_at <= end,
            )
            .scalar()
        ) or 0

        return {
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "resource_id": e.resource_id,
                    "metadata": e.metadata_ or {},
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            },
            "summary": {
                "total_study_minutes": int(total_study_minutes),
                "completed_tasks": completed_tasks,
                "completed_resources": completed_resources,
                "message_count": message_count,
            },
        }
    finally:
        db.close()


@router.get("/learner/me/history/heatmap")
def get_learning_heatmap(
    auth: AuthContext = Depends(require_auth),
    days: int = Query(default=90, ge=7, le=365),
) -> dict[str, Any]:
    """Return daily learning activity counts for a calendar heatmap."""
    db = SessionLocal()
    try:
        learner_id = auth.learner_id
        since = datetime.now(timezone.utc) - timedelta(days=days)

        rows = (
            db.query(
                func.date(LearningEventModel.created_at).label("day"),
                func.count(LearningEventModel.id).label("count"),
            )
            .filter(
                LearningEventModel.session.has(learner_id=learner_id),
                LearningEventModel.created_at >= since,
            )
            .group_by("day")
            .order_by("day")
            .all()
        )

        return {
            "days": days,
            "data": [{"date": str(row.day), "count": row.count} for row in rows],
        }
    finally:
        db.close()


@router.get("/learner/me/history/sessions")
def get_session_history(
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List the current learner's session history with per-session summary stats."""
    db = SessionLocal()
    try:
        learner_id = auth.learner_id

        base = db.query(SessionModel).filter(
            SessionModel.learner_id == learner_id
        )

        total = base.count()
        sessions = (
            base.order_by(desc(SessionModel.updated_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        result_sessions = []
        for s in sessions:
            msg_count = db.query(func.count(MessageModel.id)).filter(
                MessageModel.session_id == s.id
            ).scalar() or 0

            event_count = db.query(func.count(LearningEventModel.id)).filter(
                LearningEventModel.session_id == s.id
            ).scalar() or 0

            result_sessions.append({
                "id": s.id,
                "title": s.title,
                "subject_id": s.subject_id,
                "status": s.status,
                "message_count": msg_count,
                "event_count": event_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            })

        return {
            "sessions": result_sessions,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            },
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
