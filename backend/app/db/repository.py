"""Data access layer for EduAgent persistence.

Each function takes a SQLAlchemy Session and performs one logical operation.
This keeps queries close to the ORM while giving callers control over
transaction boundaries.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    LearnerModel,
    LearningEventModel,
    LearningPathModel,
    MessageModel,
    ProfileSnapshotModel,
    ResourceModel,
    SessionModel,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Session ──────────────────────────────────────────────────────────────

def get_or_create_session(
    db: Session,
    session_id: str,
    learner_id: str | None = None,
    subject_id: str | None = None,
) -> SessionModel:
    sess = db.get(SessionModel, session_id)
    if sess is None:
        learner = get_or_create_learner(db, learner_id)
        sess = SessionModel(
            id=session_id,
            learner_id=learner.id,
            subject_id=subject_id or None,
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
    elif subject_id and not sess.subject_id:
        # Backfill subject_id on existing session
        sess.subject_id = subject_id
        db.commit()
    return sess


def list_sessions(
    db: Session,
    status: str = "active",
    learner_id: str | None = None,
    subject_id: str | None = None,
) -> list[SessionModel]:
    q = db.query(SessionModel).filter(SessionModel.status == status)
    if learner_id:
        q = q.filter(SessionModel.learner_id == learner_id)
    if subject_id:
        q = q.filter(SessionModel.subject_id == subject_id)
    return q.order_by(desc(SessionModel.updated_at)).all()


def delete_session(db: Session, session_id: str) -> bool:
    sess = db.get(SessionModel, session_id)
    if sess is None:
        return False
    db.delete(sess)
    db.commit()
    return True


def touch_session(db: Session, session_id: str) -> None:
    sess = db.get(SessionModel, session_id)
    if sess:
        sess.updated_at = _utcnow()
        db.commit()


# ── Learners ─────────────────────────────────────────────────────────────


def get_or_create_learner(db: Session, learner_id: str | None = None) -> LearnerModel:
    """Get an existing learner by ID, or create a new one."""
    if learner_id:
        learner = db.get(LearnerModel, learner_id)
        if learner:
            return learner
    learner = LearnerModel(
        id=learner_id or str(uuid.uuid4()),
        nickname="学习者",
    )
    db.add(learner)
    db.commit()
    db.refresh(learner)
    return learner


def get_learner(db: Session, learner_id: str) -> LearnerModel | None:
    """Get a learner by ID, or None."""
    return db.get(LearnerModel, learner_id)


def get_learner_sessions(db: Session, learner_id: str) -> list[SessionModel]:
    """List all sessions belonging to a learner, newest first."""
    return (
        db.query(SessionModel)
        .filter(SessionModel.learner_id == learner_id)
        .order_by(desc(SessionModel.updated_at))
        .all()
    )


def get_learner_aggregated_profile(db: Session, learner_id: str) -> dict[str, Any] | None:
    """Merge the latest profile snapshot across all of a learner's sessions.

    Uses the most recent snapshot as the base, then fills in any missing
    dimensions from older snapshots across the learner's other sessions.
    """
    sessions = get_learner_sessions(db, learner_id)
    if not sessions:
        return None

    session_ids = [s.id for s in sessions]
    snapshots = (
        db.query(ProfileSnapshotModel)
        .filter(ProfileSnapshotModel.session_id.in_(session_ids))
        .order_by(desc(ProfileSnapshotModel.created_at))
        .all()
    )
    if not snapshots:
        return None

    # Merge dimensions: newest snapshot wins per key, older fill gaps
    merged_dims: dict[str, Any] = {}
    seen_keys: set[str] = set()
    for snap in snapshots:
        dims = snap.dimensions or []
        if isinstance(dims, list):
            for dim in dims:
                key = dim.get("key") if isinstance(dim, dict) else None
                if key and key not in seen_keys:
                    merged_dims[key] = dim
                    seen_keys.add(key)
        elif isinstance(dims, dict):
            for key, value in dims.items():
                if key not in seen_keys:
                    merged_dims[key] = value
                    seen_keys.add(key)

    return {
        "dimensions": list(merged_dims.values()),
        "weaknesses": snapshots[0].weaknesses or [],
        "preferences": snapshots[0].preferences or {},
        "readiness_score": snapshots[0].readiness_score or 0.0,
        "session_count": len(sessions),
    }


# ── Messages ─────────────────────────────────────────────────────────────

def save_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    intent: dict | None = None,
    metadata: dict | None = None,
) -> MessageModel:
    get_or_create_session(db, session_id)
    msg = MessageModel(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        metadata_=metadata,
    )
    db.add(msg)
    touch_session(db, session_id)
    db.commit()
    db.refresh(msg)
    return msg


def get_messages(db: Session, session_id: str) -> list[MessageModel]:
    return (
        db.query(MessageModel)
        .filter(MessageModel.session_id == session_id)
        .order_by(MessageModel.created_at)
        .all()
    )


def get_last_intent(db: Session, session_id: str) -> dict | None:
    msg = (
        db.query(MessageModel)
        .filter(
            MessageModel.session_id == session_id,
            MessageModel.intent.isnot(None),
        )
        .order_by(desc(MessageModel.created_at))
        .first()
    )
    return msg.intent if msg else None


# ── Profile Snapshots ────────────────────────────────────────────────────

def save_profile_snapshot(
    db: Session,
    session_id: str,
    dimensions: list[dict] | None = None,
    weaknesses: list[dict] | None = None,
    preferences: dict | None = None,
    readiness_score: float | None = None,
) -> ProfileSnapshotModel:
    get_or_create_session(db, session_id)
    snap = ProfileSnapshotModel(
        session_id=session_id,
        dimensions=dimensions,
        weaknesses=weaknesses,
        preferences=preferences,
        readiness_score=readiness_score,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def get_latest_profile(db: Session, session_id: str) -> ProfileSnapshotModel | None:
    return (
        db.query(ProfileSnapshotModel)
        .filter(ProfileSnapshotModel.session_id == session_id)
        .order_by(desc(ProfileSnapshotModel.created_at))
        .first()
    )


# ── Learning Paths ───────────────────────────────────────────────────────

def upsert_learning_path(
    db: Session,
    session_id: str,
    path_data: dict[str, Any],
) -> LearningPathModel:
    get_or_create_session(db, session_id)
    path = LearningPathModel(
        id=path_data.get("id", f"path_{session_id}"),
        session_id=session_id,
        course_id=path_data.get("course_id", ""),
        course_name=path_data.get("course_name", ""),
        description=path_data.get("description"),
        stages=path_data.get("stages"),
        overall_progress=path_data.get("overallProgress", 0),
        estimated_days=path_data.get("estimatedDays", 14),
    )
    # Merge existing if same id
    existing = db.get(LearningPathModel, path.id)
    if existing:
        existing.session_id = session_id
        existing.course_id = path.course_id
        existing.course_name = path.course_name
        existing.description = path.description
        existing.stages = path.stages
        existing.overall_progress = path.overall_progress
        existing.estimated_days = path.estimated_days
        existing.updated_at = _utcnow()
        path = existing
    else:
        db.add(path)
    db.commit()
    db.refresh(path)
    return path


def get_latest_learning_path(db: Session, session_id: str) -> LearningPathModel | None:
    return (
        db.query(LearningPathModel)
        .filter(LearningPathModel.session_id == session_id)
        .order_by(desc(LearningPathModel.updated_at))
        .first()
    )


# ── Resources ────────────────────────────────────────────────────────────

def upsert_resource(
    db: Session,
    session_id: str,
    resource_data: dict[str, Any],
) -> ResourceModel:
    get_or_create_session(db, session_id)

    res = ResourceModel(
        id=resource_data.get("id", f"res_{_utcnow().timestamp()}"),
        session_id=session_id,
        type=resource_data.get("type", "lecture"),
        title=resource_data.get("title", "学习资源"),
        description=resource_data.get("description"),
        content=resource_data.get("content"),
        knowledge_points=resource_data.get("knowledge_points") or resource_data.get("knowledgePoints"),
        tags=resource_data.get("tags"),
        difficulty=resource_data.get("difficulty", "easy"),
        estimated_minutes=resource_data.get("estimated_minutes") or resource_data.get("estimatedMinutes", 20),
        format=resource_data.get("format", "text"),
        mermaid_def=resource_data.get("mermaid_def") or resource_data.get("mermaidDef"),
        code_blocks=resource_data.get("code_blocks") or resource_data.get("codeBlocks"),
        questions=resource_data.get("questions"),
        ppt_outline=resource_data.get("ppt_outline") or resource_data.get("pptOutline"),
        bookmarked=resource_data.get("bookmarked", False),
        study_status=resource_data.get("study_status") or resource_data.get("studyStatus", "new"),
        completed_at=_utcnow() if (resource_data.get("study_status") or resource_data.get("studyStatus", "")) == "completed" else resource_data.get("completed_at"),
        source=resource_data.get("source", "agent_generated"),
        related_stage_id=resource_data.get("related_stage_id", ""),
        task_id=resource_data.get("task_id", ""),
    )
    existing = db.get(ResourceModel, res.id)
    if existing:
        existing.session_id = session_id
        existing.type = res.type
        existing.title = res.title
        existing.description = res.description
        existing.content = res.content
        existing.knowledge_points = res.knowledge_points
        existing.tags = res.tags
        existing.difficulty = res.difficulty
        existing.estimated_minutes = res.estimated_minutes
        existing.format = res.format
        existing.mermaid_def = res.mermaid_def
        existing.code_blocks = res.code_blocks
        existing.questions = res.questions
        existing.ppt_outline = res.ppt_outline
        existing.bookmarked = res.bookmarked
        existing.study_status = res.study_status
        existing.completed_at = res.completed_at
        existing.source = res.source
        existing.related_stage_id = res.related_stage_id
        existing.task_id = res.task_id
        existing.updated_at = _utcnow()
        res = existing
    else:
        db.add(res)
    db.commit()
    db.refresh(res)
    return res


def get_resources(db: Session, session_id: str) -> list[ResourceModel]:
    return (
        db.query(ResourceModel)
        .filter(ResourceModel.session_id == session_id)
        .order_by(desc(ResourceModel.created_at))
        .all()
    )


def get_resource(db: Session, resource_id: str, session_id: str) -> ResourceModel | None:
    return (
        db.query(ResourceModel)
        .filter(ResourceModel.id == resource_id, ResourceModel.session_id == session_id)
        .first()
    )


def delete_resource(db: Session, session_id: str, resource_id: str) -> bool:
    """Delete a resource by ID, scoped to session. Returns True if deleted."""
    resource = (
        db.query(ResourceModel)
        .filter(ResourceModel.id == resource_id, ResourceModel.session_id == session_id)
        .first()
    )
    if resource:
        db.delete(resource)
        db.commit()
        return True
    return False


def update_resource_study_status(db: Session, session_id: str, resource_id: str, study_status: str) -> bool:
    """Update the study status of a resource (new / in_progress / completed).

    Scoped to session — only modifies the resource if it belongs to the given session.
    Returns True if a resource was found and updated, False otherwise.
    """
    resource = (
        db.query(ResourceModel)
        .filter(ResourceModel.id == resource_id, ResourceModel.session_id == session_id)
        .first()
    )
    if resource:
        resource.study_status = study_status
        if study_status == "completed":
            resource.completed_at = _utcnow()
        elif study_status == "new":
            resource.completed_at = None
        db.commit()
        return True
    return False


def toggle_bookmark(db: Session, session_id: str, resource_id: str) -> bool | None:
    res = (
        db.query(ResourceModel)
        .filter(ResourceModel.id == resource_id, ResourceModel.session_id == session_id)
        .first()
    )
    if res is None:
        return None
    res.bookmarked = not res.bookmarked
    db.commit()
    return res.bookmarked


def get_bookmarked_ids(db: Session, session_id: str) -> set[str]:
    rows = (
        db.query(ResourceModel.id)
        .filter(
            ResourceModel.session_id == session_id,
            ResourceModel.bookmarked.is_(True),
        )
        .all()
    )
    return {row[0] for row in rows}


# ── Batch operations ──────────────────────────────────────────────────

def batch_update_study_status(
    db: Session,
    session_id: str,
    resource_ids: list[str],
    study_status: str,
) -> int:
    """Batch update study status for multiple resources in a session.
    Returns the number of resources updated."""
    updated = (
        db.query(ResourceModel)
        .filter(
            ResourceModel.session_id == session_id,
            ResourceModel.id.in_(resource_ids),
        )
        .update({"study_status": study_status}, synchronize_session="fetch")
    )
    db.commit()
    return updated


def batch_set_bookmark(
    db: Session,
    session_id: str,
    resource_ids: list[str],
    bookmarked: bool,
) -> int:
    """Batch set bookmark state for multiple resources in a session.
    Returns the number of resources updated."""
    updated = (
        db.query(ResourceModel)
        .filter(
            ResourceModel.session_id == session_id,
            ResourceModel.id.in_(resource_ids),
        )
        .update({"bookmarked": bookmarked}, synchronize_session="fetch")
    )
    db.commit()
    return updated


# ── Learning Events ──────────────────────────────────────────────────────


def check_resource_complete_duplicate(
    db: Session, session_id: str, resource_id: str
) -> bool:
    """Return True if a resource_complete event already exists for this (session, resource).

    Used to implement idempotent resource_complete semantics: completing the
    same resource multiple times should only count once.
    """
    if not resource_id:
        return False
    return db.query(LearningEventModel).filter(
        LearningEventModel.session_id == session_id,
        LearningEventModel.event_type == "resource_complete",
        LearningEventModel.resource_id == resource_id,
    ).first() is not None


def check_resource_view_duplicate(
    db: Session, session_id: str, resource_id: str, window_seconds: int = 300
) -> bool:
    """Return True if a resource_view exists for this (session, resource) within window_seconds.

    Prevents rapid double-clicks from inflating view counts. Views spaced more
    than window_seconds apart are both recorded (cumulative tracking).
    """
    if not resource_id:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    return db.query(LearningEventModel).filter(
        LearningEventModel.session_id == session_id,
        LearningEventModel.event_type == "resource_view",
        LearningEventModel.resource_id == resource_id,
        LearningEventModel.created_at >= cutoff,
    ).first() is not None


def log_event(
    db: Session,
    session_id: str,
    event_type: str,
    resource_id: str | None = None,
    metadata: dict | None = None,
    skip_duplicate_check: bool = False,
) -> LearningEventModel | None:
    """Log a learning event, skipping duplicates per dedup policy.

    Returns ``None`` when the event is silently dropped as a duplicate.
    Callers should handle ``None`` gracefully.

    Dedup policy (applied unless *skip_duplicate_check* is True):

    - ``resource_complete``: idempotent — only the first completion per
      (session, resource) is stored.
    - ``resource_view``: time-window dedup — duplicates within
      ``event_dedup_view_window_seconds`` (default 300 s) are dropped.
    - All other event types are never deduped.
    """
    # ── Deduplication checks ──────────────────────────────────────────
    if not skip_duplicate_check and event_type == "resource_complete" and resource_id:
        if check_resource_complete_duplicate(db, session_id, resource_id):
            logger.debug(
                "Dedup: skipped duplicate resource_complete session=%s resource=%s",
                session_id, resource_id,
            )
            return None

    if not skip_duplicate_check and event_type == "resource_view" and resource_id:
        from app.config import settings
        if check_resource_view_duplicate(
            db, session_id, resource_id,
            settings.event_dedup_view_window_seconds,
        ):
            logger.debug(
                "Dedup: skipped duplicate resource_view session=%s resource=%s (within window)",
                session_id, resource_id,
            )
            return None

    get_or_create_session(db, session_id)
    evt = LearningEventModel(
        session_id=session_id,
        event_type=event_type,
        resource_id=resource_id,
        metadata_=metadata,
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt


def get_events(
    db: Session,
    session_id: str | None = None,
    limit: int | None = None,
) -> list[LearningEventModel]:
    if not session_id:
        return []
    q = db.query(LearningEventModel)
    q = q.filter(LearningEventModel.session_id == session_id)
    q = q.order_by(desc(LearningEventModel.created_at))
    if limit:
        q = q.limit(limit)
    return q.all()


def get_event_analytics(db: Session, session_id: str) -> dict[str, Any]:
    """Compute analytics summary from learning events (mirrors LearningTracker.summary)."""
    events = get_events(db, session_id)

    total_minutes = 0
    resource_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    quiz_correct = 0
    quiz_total = 0
    quiz_scores: list[float] = []
    resource_titles: dict[str, str] = {}
    topic_wrong: dict[str, int] = {}
    topic_total: dict[str, int] = {}

    # Quiz latest/best tracking
    quiz_results: list[dict[str, Any]] = []  # (score, topic, timestamp) tuples
    # Feedback stats
    feedback_ratings: list[int] = []
    feedback_count: int = 0

    # Compute last study time (max timestamp)
    last_study_ts: float | None = None

    for evt in events:
        meta = evt.metadata_ or {}
        # Duration
        duration = meta.get("duration") or meta.get("durationMinutes") or 0
        try:
            total_minutes += max(0, int(duration))
        except (TypeError, ValueError):
            pass

        # Last study time
        if evt.created_at:
            ts = evt.created_at.timestamp()
            if last_study_ts is None or ts > last_study_ts:
                last_study_ts = ts

        # Resource counter (only real resource events, not node_progress)
        _RESOURCE_EVENTS = {"resource_view", "resource_complete", "quiz_result", "quiz_submit", "feedback"}
        if evt.resource_id and evt.event_type in _RESOURCE_EVENTS:
            resource_counts[evt.resource_id] = resource_counts.get(evt.resource_id, 0) + 1
            # Capture resource title from metadata
            if meta.get("title"):
                resource_titles[evt.resource_id] = str(meta["title"])

        # Event counter
        etype = evt.event_type or "unknown"
        event_counts[etype] = event_counts.get(etype, 0) + 1

        # Quiz accuracy
        if etype in {"quiz_submit", "quiz_result", "practice_result"}:
            if "accuracy" in meta:
                try:
                    quiz_scores.append(float(meta["accuracy"]))
                except (TypeError, ValueError):
                    pass
            if "score" in meta:
                try:
                    quiz_scores.append(float(meta["score"]))
                except (TypeError, ValueError):
                    pass
            if "correct" in meta and "total" in meta:
                try:
                    quiz_correct += int(meta["correct"])
                    quiz_total += int(meta["total"])
                except (TypeError, ValueError):
                    pass
            # Track individual quiz result for latest/best
            quiz_pct: float | None = None
            if "accuracy" in meta:
                try:
                    a = float(meta["accuracy"])
                    quiz_pct = round(a * 100) if a <= 1 else round(a)
                except (TypeError, ValueError):
                    pass
            if quiz_pct is None and "score" in meta:
                try:
                    s = float(meta["score"])
                    quiz_pct = round(s * 100) if s <= 1 else round(s)
                except (TypeError, ValueError):
                    pass
            if quiz_pct is None and "correct" in meta and "total" in meta:
                try:
                    c = int(meta["correct"])
                    t = int(meta["total"])
                    if t > 0:
                        quiz_pct = round(c / t * 100)
                except (TypeError, ValueError):
                    pass
            if quiz_pct is not None:
                quiz_results.append({
                    "score": quiz_pct,
                    "topic": meta.get("topic") or meta.get("knowledgePoint") or "",
                    "timestamp": evt.created_at.isoformat() if evt.created_at else "",
                })

        # Feedback stats
        if etype == "feedback":
            feedback_count += 1
            rating = meta.get("rating")
            if rating is not None:
                try:
                    feedback_ratings.append(int(rating))
                except (TypeError, ValueError):
                    pass

        # Topic stats
        topic = meta.get("topic") or meta.get("knowledgePoint")
        if topic:
            key = str(topic)
            topic_total[key] = topic_total.get(key, 0) + int(meta.get("total", 1) or 1)
            topic_wrong[key] = topic_wrong.get(key, 0) + int(meta.get("wrong", 0) or 0)

    # Quiz accuracy
    quiz_accuracy: int | None = None
    if quiz_total > 0:
        quiz_accuracy = round(quiz_correct / quiz_total * 100)
    elif quiz_scores:
        normalized = [s * 100 if s <= 1 else s for s in quiz_scores]
        quiz_accuracy = round(sum(normalized) / len(normalized))

    # Quiz latest/best
    latest_quiz_score: dict[str, Any] | None = None
    best_quiz_score: dict[str, Any] | None = None
    if quiz_results:
        latest_quiz_score = quiz_results[-1]  # last chronological entry
        best_quiz_score = max(quiz_results, key=lambda r: r["score"])
        latest_quiz_score["source"] = "analytics"
        latest_quiz_score["quality_status"] = "computed"
        best_quiz_score["source"] = "analytics"
        best_quiz_score["quality_status"] = "computed"

    # Feedback stats
    feedback_stats: dict[str, Any] | None = None
    if feedback_count > 0:
        avg_rating = round(sum(feedback_ratings) / len(feedback_ratings), 1) if feedback_ratings else None
        feedback_stats = {
            "count": feedback_count,
            "averageRating": avg_rating,
            "source": "analytics",
            "quality_status": "computed",
            "evidence": f"{feedback_count} feedback event(s) with {len(feedback_ratings)} rating(s)",
        }

    # Weak topics — enhanced with source tracking
    topic_sources: dict[str, set[str]] = {}
    for evt in events:
        meta = evt.metadata_ or {}
        topic = meta.get("topic") or meta.get("knowledgePoint")
        if not topic:
            continue
        tk = str(topic)
        if tk not in topic_sources:
            topic_sources[tk] = set()
        if evt.event_type in ("quiz_result", "quiz_submit"):
            topic_sources[tk].add("quiz")
        elif evt.event_type == "practice_result":
            topic_sources[tk].add("practice")
        elif evt.event_type == "feedback":
            topic_sources[tk].add("feedback")
        elif evt.event_type == "diagnosis":
            topic_sources[tk].add("diagnosis")

    ranked = sorted(
        topic_wrong.items(),
        key=lambda item: (item[1] / max(1, topic_total.get(item[0], 1)), item[1]),
        reverse=True,
    )
    weak_topics = [
        {
            "topic": topic,
            "wrongCount": wrong,
            "totalCount": topic_total.get(topic, 1),
            "risk": round(wrong / max(1, topic_total.get(topic, 1)), 2),
            "source": sorted(topic_sources.get(topic, ["diagnosis"])),
            "priority": "high" if wrong / max(1, topic_total.get(topic, 1)) > 0.5 else "medium",
        }
        for topic, wrong in ranked[:5]
        if wrong > 0
    ]

    # ── Structured recommendations from 5 sources ──
    try:
        session_resources = get_resources(db, session_id)
    except SQLAlchemyError:
        session_resources = []

    try:
        session_path = get_latest_learning_path(db, session_id)
    except SQLAlchemyError:
        session_path = None

    from app.services.recommendation_engine import generate_recommendations

    recommendations_raw = generate_recommendations(
        session_id=session_id,
        weak_topics=weak_topics,
        resources=session_resources,
        learning_path=session_path,
        db=db,
    )
    recommendations = recommendations_raw

    # ── Chart data: completion trend (last 14 days) ──
    from collections import defaultdict as _dd
    daily_completions: dict[str, int] = _dd(int)
    daily_minutes: dict[str, int] = _dd(int)
    daily_quiz: list[dict[str, Any]] = []
    resource_type_counts: dict[str, int] = _dd(int)

    for evt in events:
        meta = evt.metadata_ or {}
        day_key = evt.created_at.strftime("%Y-%m-%d") if evt.created_at else ""

        # Daily minutes tracking
        duration = meta.get("duration") or meta.get("durationMinutes") or 0
        try:
            daily_minutes[day_key] += max(0, int(duration))
        except (TypeError, ValueError):
            pass

        # Completion trend
        if evt.event_type == "resource_complete" and day_key:
            daily_completions[day_key] += 1

        # Quiz trend — collect individual accuracy points
        if evt.event_type in ("quiz_result", "quiz_submit", "practice_result"):
            accuracy = meta.get("accuracy")
            score = meta.get("score")
            pct = None
            if accuracy is not None:
                try:
                    pct = round(float(accuracy) * 100) if float(accuracy) <= 1 else round(float(accuracy))
                except (TypeError, ValueError):
                    pass
            if pct is None and score is not None:
                try:
                    pct = round(float(score) * 100) if float(score) <= 1 else round(float(score))
                except (TypeError, ValueError):
                    pass
            if pct is not None:
                daily_quiz.append({
                    "date": day_key,
                    "accuracy": pct,
                    "topic": meta.get("topic") or meta.get("knowledgePoint") or "",
                    "timestamp": evt.created_at.isoformat() if evt.created_at else "",
                })

        # Resource type usage
        rtype = meta.get("type", "")
        if rtype and evt.resource_id and evt.event_type in _RESOURCE_EVENTS:
            resource_type_counts[rtype] += 1

    # Also read resource type from ResourceModel for a more complete picture
    try:
        resource_rows = (
            db.query(ResourceModel.type, ResourceModel.id)
            .filter(ResourceModel.session_id == session_id)
            .all()
        )
        for rtype, rid in resource_rows:
            if rid in resource_counts and rtype:
                resource_type_counts[rtype] = max(
                    resource_type_counts.get(rtype, 0),
                    resource_counts.get(rid, 0),
                )
    except SQLAlchemyError:
        import logging
        logging.getLogger("app.db.repository").warning(
            "Failed to resolve resource types for analytics", exc_info=True
        )

    top_resources = sorted(resource_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Build completion trend array (last 14 days)
    import datetime as _dt
    today = _dt.date.today()
    completion_trend = []
    for i in range(13, -1, -1):
        d = today - _dt.timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        completion_trend.append({
            "date": ds,
            "count": daily_completions.get(ds, 0),
        })

    # ── Today study minutes ──
    today_str = today.strftime("%Y-%m-%d")
    today_study_minutes = daily_minutes.get(today_str, 0)

    # ── Streak: consecutive days with any learning activity ──
    streak = 0
    check_date = today
    while True:
        ds = check_date.strftime("%Y-%m-%d")
        if daily_minutes.get(ds, 0) > 0 or daily_completions.get(ds, 0) > 0:
            streak += 1
            check_date = check_date - _dt.timedelta(days=1)
        else:
            break

    return {
        "eventCount": len(events),
        "totalStudyMinutes": total_minutes,
        "todayStudyMinutes": today_study_minutes,
        "streak": streak,
        "activeResourceCount": len(resource_counts),
        "viewedResources": event_counts.get("resource_view", 0),
        "completedResources": event_counts.get("resource_complete", 0),
        "practiceCount": event_counts.get("practice_result", 0),
        "resourceViewCount": event_counts.get("resource_view", 0),
        "resourceCompleteCount": event_counts.get("resource_complete", 0),
        "lastStudyTime": int(last_study_ts * 1000) if last_study_ts else None,
        "eventBreakdown": event_counts,
        "topResources": [
            {"resourceId": rid, "count": cnt, "title": resource_titles.get(rid, "")} for rid, cnt in top_resources
        ],
        "quizAccuracy": quiz_accuracy,
        "weakTopics": weak_topics,
        "recommendations": recommendations,
        "completionTrend": completion_trend,
        "quizTrend": daily_quiz[-20:],  # last 20 quiz results
        # Quiz latest/best for explicit clarity (requirement: "latest / best 要清楚")
        "latestQuizScore": latest_quiz_score,
        "bestQuizScore": best_quiz_score,
        # Feedback explainable stats (requirement: "统计要可解释")
        "feedbackStats": feedback_stats,
        "resourceTypeBreakdown": dict(sorted(resource_type_counts.items(), key=lambda x: x[1], reverse=True)),
        "recentEvents": [
            {
                "event": evt.event_type,
                "resourceId": evt.resource_id,
                "metadata": evt.metadata_,
                "timestamp": evt.created_at.isoformat() if evt.created_at else None,
            }
            for evt in events[:5]
        ],
    }
