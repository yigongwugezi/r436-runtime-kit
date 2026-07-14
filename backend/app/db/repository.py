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
    AnswerRecordModel,
    AttemptModel,
    DailyTaskModel,
    ExamSetModel,
    LearnerModel,
    LearningEventModel,
    LearningPathModel,
    MessageModel,
    PracticeQuestionModel,
    ProfileSnapshotModel,
    QuizModel,
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


# ── User Preferences ─────────────────────────────────────────────────────


def get_user_preferences(db: Session, learner_id: str) -> dict[str, Any]:
    """Get the preferences JSON blob for a learner, or empty dict."""
    from app.db.models import UserPreferencesModel

    prefs = db.get(UserPreferencesModel, learner_id)
    return prefs.preferences if prefs else {}


def save_user_preferences(
    db: Session, learner_id: str, preferences: dict[str, Any]
) -> dict[str, Any]:
    """Upsert preferences for a learner. Returns the saved preferences dict."""
    from app.db.models import UserPreferencesModel

    prefs = db.get(UserPreferencesModel, learner_id)
    if prefs is None:
        prefs = UserPreferencesModel(
            learner_id=learner_id,
            preferences=preferences,
        )
        db.add(prefs)
    else:
        prefs.preferences = preferences
    db.commit()
    db.refresh(prefs)
    return prefs.preferences


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
        resource_metadata=resource_data.get("resource_metadata") or resource_data.get("metadata"),
        bookmarked=resource_data.get("bookmarked", False),
        study_status=resource_data.get("study_status") or resource_data.get("studyStatus", "new"),
        completed_at=_utcnow() if (resource_data.get("study_status") or resource_data.get("studyStatus", "")) == "completed" else resource_data.get("completed_at"),
        source=resource_data.get("source", "agent_generated"),
        related_stage_id=resource_data.get("related_stage_id", ""),
        related_chapter_id=resource_data.get("related_chapter_id", ""),
        related_section_id=resource_data.get("related_section_id", ""),
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
        existing.resource_metadata = res.resource_metadata
        existing.bookmarked = res.bookmarked
        existing.study_status = res.study_status
        existing.completed_at = res.completed_at
        existing.source = res.source
        existing.related_stage_id = res.related_stage_id
        existing.related_chapter_id = res.related_chapter_id
        existing.related_section_id = res.related_section_id
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

    # ── Mode-specific metrics ──
    mode_metrics: dict[str, int] = {}
    for mode_evt in ("vocabulary_review", "listening_practice", "speaking_practice",
                     "writing_practice", "grammar_exercise", "code_practice", "project_milestone"):
        if event_counts.get(mode_evt, 0) > 0:
            mode_metrics[mode_evt] = event_counts[mode_evt]

    # ── 知识点掌握趋势（按知识点分组的 quiz 结果序列）──
    topic_trend: dict[str, list[dict[str, Any]]] = {}
    for qr in daily_quiz:
        t = qr.get("topic", "") or "general"
        if t not in topic_trend:
            topic_trend[t] = []
        topic_trend[t].append({"date": qr["date"], "accuracy": qr["accuracy"]})
    topic_mastery_trend = [
        {"topic": t, "points": pts[-10:]}
        for t, pts in topic_trend.items()
        if len(pts) >= 2
    ]

    # ── 学习规律评分（根据每日学习间隔）──
    import datetime as _dt2
    active_days: list[_dt2.date] = []
    for evt in events:
        if evt.created_at:
            d = evt.created_at.date()
            if d not in active_days:
                active_days.append(d)
    active_days.sort()
    regularity_score = 50  # 默认中等
    if len(active_days) >= 3:
        gaps = [(active_days[i+1] - active_days[i]).days for i in range(len(active_days)-1)]
        if gaps:
            import statistics
            gap_std = statistics.stdev(gaps) if len(gaps) > 1 else 0
            # std 越小越规律：std=0 → 100分，std=7 → 50分
            regularity_score = max(0, min(100, round(100 - gap_std * 7)))

    # ── 综合评估摘要 ──
    assessment_parts = []
    if total_minutes > 0:
        assessment_parts.append(f"累计学习了 {total_minutes} 分钟")
    if streak > 0:
        assessment_parts.append(f"连续学习 {streak} 天")
    if total_minutes > 0 and quiz_accuracy is not None:
        if quiz_accuracy >= 80:
            assessment_parts.append("掌握情况良好")
        elif quiz_accuracy >= 60:
            assessment_parts.append("掌握情况中等，有提升空间")
        else:
            assessment_parts.append("基础较薄弱，建议从核心概念开始复习")
    if regularity_score >= 70:
        assessment_parts.append("学习规律性强")
    elif regularity_score <= 30 and len(active_days) >= 3:
        assessment_parts.append("学习间隔不规律，建议固定每天的学习时间")
    if weak_topics:
        topics_str = "、".join([w["topic"] for w in weak_topics[:3]])
        assessment_parts.append(f"重点关注：{topics_str}")
    assessment_summary = "。".join(assessment_parts) + "。" if assessment_parts else "暂无足够数据生成评估。"

    return {
        "eventCount": len(events),
        "totalStudyMinutes": total_minutes,
        "todayStudyMinutes": today_study_minutes,
        "streak": streak,
        "activeResourceCount": len(resource_counts),
        "modeMetrics": mode_metrics if mode_metrics else None,
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
        "assessmentSummary": assessment_summary,
        "regularityScore": regularity_score,
        "topicMasteryTrend": topic_mastery_trend,
    }


# ── Daily Tasks ──────────────────────────────────────────────────────────


def upsert_daily_tasks(
    db: Session,
    session_id: str,
    tasks: list[dict[str, Any]],
) -> int:
    """Batch upsert daily tasks for a session.

    Deletes existing tasks for the session and inserts the new set.
    This is called when a learning path is (re)generated.

    Returns the number of tasks inserted.
    """
    db.query(DailyTaskModel).filter(
        DailyTaskModel.session_id == session_id
    ).delete()

    count = 0
    for t in tasks:
        task = DailyTaskModel(
            session_id=session_id,
            stage_id=t.get("stage_id", ""),
            day_index=t.get("day_index", 1),
            day_label=t.get("day_label", f"第{t.get('day_index', 1)}天"),
            title=t.get("title", ""),
            description=t.get("description"),
            source=t.get("source", "agent_generated"),
        )
        db.add(task)
        count += 1
    db.commit()
    return count


def get_daily_tasks(
    db: Session,
    session_id: str,
    day_index: int | None = None,
) -> list[DailyTaskModel]:
    """Get daily tasks for a session, optionally filtered by day index."""
    q = db.query(DailyTaskModel).filter(
        DailyTaskModel.session_id == session_id
    )
    if day_index is not None:
        q = q.filter(DailyTaskModel.day_index == day_index)
    return q.order_by(DailyTaskModel.day_index, DailyTaskModel.id).all()


def get_daily_tasks_for_learner(
    db: Session,
    learner_id: str,
    day_index: int,
) -> list[dict[str, Any]]:
    """Cross-subject: get all daily tasks for a learner on a specific day.

    Joins through sessions to find all of a learner's sessions,
    then fetches tasks for each session filtered by day_index.
    Returns enriched dicts with session/subject metadata.
    """
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.learner_id == learner_id)
        .all()
    )

    results: list[dict[str, Any]] = []
    for sess in sessions:
        tasks = (
            db.query(DailyTaskModel)
            .filter(
                DailyTaskModel.session_id == sess.id,
                DailyTaskModel.day_index == day_index,
            )
            .order_by(DailyTaskModel.id)
            .all()
        )
        for t in tasks:
            results.append({
                "id": t.id,
                "sessionId": sess.id,
                "subjectId": sess.subject_id or "",
                "subjectName": sess.title or "未命名科目",
                "stageId": t.stage_id,
                "dayIndex": t.day_index,
                "dayLabel": t.day_label,
                "title": t.title,
                "description": t.description,
                "completed": t.completed,
                "completedAt": int(t.completed_at.timestamp() * 1000) if t.completed_at else None,
                "source": t.source,
            })

    return results


def update_task_completion(
    db: Session,
    task_id: int,
    session_id: str,
    completed: bool,
) -> DailyTaskModel | None:
    """Toggle completion state of a single daily task.

    Scoped to session_id to enforce subject isolation:
    a task's session must match the provided session_id.
    """
    task = db.query(DailyTaskModel).filter(
        DailyTaskModel.id == task_id,
        DailyTaskModel.session_id == session_id,
    ).first()
    if task is None:
        return None
    task.completed = completed
    task.completed_at = datetime.now(timezone.utc) if completed else None
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


# ── Questions（M3）────────────────────────────────────────────────────────


def upsert_questions(db: Session, session_id: str, questions: list[dict]) -> int:
    """批量 upsert 题目。返回写入数量。"""
    count = 0
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("question_id", ""))
        if not qid:
            continue
        existing = db.query(PracticeQuestionModel).filter(
            PracticeQuestionModel.question_id == qid,
            PracticeQuestionModel.session_id == session_id,
        ).first()
        if existing:
            existing.type = str(q.get("type", existing.type))
            existing.stem = str(q.get("stem", existing.stem))
            existing.options = q.get("options") if q.get("options") is not None else existing.options
            existing.correct = str(q.get("correct", "")) if q.get("correct") else existing.correct
            existing.explanation = str(q.get("explanation", "")) if q.get("explanation") else existing.explanation
            existing.difficulty = str(q.get("difficulty", "medium"))
            existing.knowledge_points = q.get("knowledge_points") if q.get("knowledge_points") is not None else existing.knowledge_points
            existing.tags = q.get("tags") if q.get("tags") is not None else existing.tags
            existing.scoring_rubric = q.get("scoring_rubric") if q.get("scoring_rubric") is not None else existing.scoring_rubric
            existing.reference_answer = str(q.get("reference_answer", "")) if q.get("reference_answer") else existing.reference_answer
            existing.source = str(q.get("source", "llm_generated"))
            existing.quality_status = str(q.get("quality_status", "passed"))
        else:
            existing = PracticeQuestionModel(
                question_id=qid,
                question_set_id=str(q.get("question_set_id", "")),
                session_id=session_id,
                type=str(q.get("type", "choice")),
                stem=str(q.get("stem", "")),
                options=q.get("options"),
                correct=str(q.get("correct", "")),
                explanation=str(q.get("explanation", "")),
                difficulty=str(q.get("difficulty", "medium")),
                knowledge_points=q.get("knowledge_points"),
                tags=q.get("tags"),
                scoring_rubric=q.get("scoring_rubric"),
                reference_answer=str(q.get("reference_answer", "")) if q.get("reference_answer") else None,
                source=str(q.get("source", "llm_generated")),
                quality_status=str(q.get("quality_status", "passed")),
            )
            db.add(existing)
        count += 1
    db.commit()
    return count


def get_questions(db: Session, session_id: str,
                  knowledge_point: str = "", difficulty: str = "", qtype: str = "",
                  limit: int = 50) -> list[PracticeQuestionModel]:
    """查询题目列表，支持过滤。"""
    q = db.query(PracticeQuestionModel).filter(PracticeQuestionModel.session_id == session_id)
    if qtype:
        q = q.filter(PracticeQuestionModel.type == qtype)
    if difficulty:
        q = q.filter(PracticeQuestionModel.difficulty == difficulty)
    rows = q.order_by(PracticeQuestionModel.created_at.desc()).limit(limit).all()
    if knowledge_point:
        rows = [r for r in rows if isinstance(r.knowledge_points, (list, dict))
                and knowledge_point in str(r.knowledge_points)]
    return rows


def get_question_by_id(db: Session, question_id: str, session_id: str = "") -> PracticeQuestionModel | None:
    q = db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_id == question_id)
    if session_id:
        q = q.filter(PracticeQuestionModel.session_id == session_id)
    return q.first()


# ── Answer Records（M4）─────────────────────────────────────────────────────


def save_answer_record(db: Session, record: dict) -> AnswerRecordModel:
    r = AnswerRecordModel(
        session_id=str(record.get("session_id", "")),
        question_id=str(record.get("question_id", "")),
        student_answer=str(record.get("student_answer", "")),
        total_score=record.get("total_score"),
        dimension_scores=record.get("dimension_scores"),
        dimension_feedback=record.get("dimension_feedback"),
        error_type=str(record.get("error_type", "")) if record.get("error_type") else None,
        error_label=str(record.get("error_label", "")) if record.get("error_label") else None,
        error_explanation=str(record.get("error_explanation", "")) if record.get("error_explanation") else None,
        error_action=str(record.get("error_action", "")) if record.get("error_action") else None,
        suggestions=record.get("suggestions"),
        strengths=record.get("strengths"),
        source=str(record.get("source", "llm_generated")),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get_answer_history(db: Session, session_id: str, limit: int = 50) -> list[AnswerRecordModel]:
    return db.query(AnswerRecordModel).filter(
        AnswerRecordModel.session_id == session_id
    ).order_by(AnswerRecordModel.created_at.desc()).limit(limit).all()


def get_weak_records(db: Session, session_id: str, error_type: str = "",
                     limit: int = 20) -> list[AnswerRecordModel]:
    q = db.query(AnswerRecordModel).filter(
        AnswerRecordModel.session_id == session_id,
        AnswerRecordModel.error_type.isnot(None),
        AnswerRecordModel.error_type != "null",
        AnswerRecordModel.error_type != "",
    )
    if error_type:
        q = q.filter(AnswerRecordModel.error_type == error_type)
    return q.order_by(AnswerRecordModel.created_at.desc()).limit(limit).all()


def get_answer_stats(db: Session, session_id: str) -> dict:
    records = db.query(AnswerRecordModel).filter(
        AnswerRecordModel.session_id == session_id
    ).all()
    total = len(records)
    correct = sum(1 for r in records if r.total_score is not None and r.total_score >= 60)
    return {"totalAttempted": total, "totalCorrect": correct}


# ── Quiz (M5) ──────────────────────────────────────────────────────────


def save_quiz(db: Session, quiz_data: dict) -> QuizModel:
    """Create a new instant quiz. Returns the saved QuizModel."""
    quiz = QuizModel(
        id=quiz_data.get("id", f"quiz_{uuid.uuid4().hex[:12]}"),
        title=quiz_data.get("title", ""),
        session_id=quiz_data.get("session_id", ""),
        scope_type=quiz_data.get("scope_type", "knowledge_point"),
        scope_id=quiz_data.get("scope_id"),
        path_id=quiz_data.get("path_id"),
        stage_id=quiz_data.get("stage_id"),
        chapter_id=quiz_data.get("chapter_id"),
        section_id=quiz_data.get("section_id"),
        knowledge_point_ids=quiz_data.get("knowledge_point_ids"),
        difficulty=quiz_data.get("difficulty", "medium"),
        question_count=quiz_data.get("question_count", 0),
        questions=quiz_data.get("questions"),
        source=quiz_data.get("source", "llm_generated"),
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


def get_quiz(db: Session, quiz_id: str) -> QuizModel | None:
    """Get a quiz by its primary-key id."""
    return db.get(QuizModel, quiz_id)


def list_quizzes(
    db: Session, session_id: str = "", scope_type: str = ""
) -> list[QuizModel]:
    """List quizzes, optionally filtered by session and scope type."""
    q = db.query(QuizModel)
    if session_id:
        q = q.filter(QuizModel.session_id == session_id)
    if scope_type:
        q = q.filter(QuizModel.scope_type == scope_type)
    return q.order_by(desc(QuizModel.created_at)).all()


def delete_quiz(db: Session, quiz_id: str) -> bool:
    """Delete a quiz by id. Returns True if deleted."""
    quiz = db.get(QuizModel, quiz_id)
    if quiz is None:
        return False
    db.delete(quiz)
    db.commit()
    return True


# ── Exam Set ──────────────────────────────────────────────────────────


def save_exam_set(db: Session, exam_data: dict) -> ExamSetModel:
    """Create a new exam set. Returns the saved ExamSetModel."""
    exam = ExamSetModel(
        id=exam_data.get("id", f"exam_{uuid.uuid4().hex[:12]}"),
        title=exam_data.get("title", ""),
        session_id=exam_data.get("session_id", ""),
        scope_type=exam_data.get("scope_type", "chapter"),
        scope_id=exam_data.get("scope_id"),
        path_id=exam_data.get("path_id"),
        stage_id=exam_data.get("stage_id"),
        chapter_id=exam_data.get("chapter_id"),
        knowledge_point_ids=exam_data.get("knowledge_point_ids"),
        difficulty=exam_data.get("difficulty", "medium"),
        difficulty_distribution=exam_data.get("difficulty_distribution"),
        question_count=exam_data.get("question_count", 0),
        questions=exam_data.get("questions"),
        estimated_minutes=exam_data.get("estimated_minutes", 30),
        total_score=exam_data.get("total_score", 100),
        source=exam_data.get("source", "llm_generated"),
        archive_policy=exam_data.get("archive_policy", "archive"),
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def get_exam_set(db: Session, exam_set_id: str) -> ExamSetModel | None:
    """Get an exam set by its primary-key id."""
    return db.get(ExamSetModel, exam_set_id)


def list_exam_sets(
    db: Session,
    session_id: str = "",
    scope_type: str = "",
    status: str = "",
) -> list[ExamSetModel]:
    """List exam sets, optionally filtered by session, scope type, or status."""
    q = db.query(ExamSetModel)
    if session_id:
        q = q.filter(ExamSetModel.session_id == session_id)
    if scope_type:
        q = q.filter(ExamSetModel.scope_type == scope_type)
    if status:
        q = q.filter(ExamSetModel.status == status)
    return q.order_by(desc(ExamSetModel.created_at)).all()


def update_exam_set(db: Session, exam_set_id: str, data: dict) -> ExamSetModel | None:
    """Partial-update an exam set. Returns the updated model or None."""
    exam = db.get(ExamSetModel, exam_set_id)
    if exam is None:
        return None
    for key in ("title", "status", "difficulty", "question_count",
                "estimated_minutes", "total_score"):
        if key in data and data[key] is not None:
            setattr(exam, key, data[key])
    for key in ("questions", "difficulty_distribution", "knowledge_point_ids"):
        if key in data and data[key] is not None:
            setattr(exam, key, data[key])
    db.commit()
    db.refresh(exam)
    return exam


def delete_exam_set(db: Session, exam_set_id: str) -> bool:
    """Delete an exam set by id. Returns True if deleted."""
    exam = db.get(ExamSetModel, exam_set_id)
    if exam is None:
        return False
    db.delete(exam)
    db.commit()
    return True


# ── Attempt ──────────────────────────────────────────────────────────


def create_attempt(db: Session, attempt_data: dict) -> AttemptModel:
    """Create a new attempt for a quiz or exam set. Returns the saved model."""
    attempt = AttemptModel(
        attempt_id=attempt_data.get("attempt_id", f"att_{uuid.uuid4().hex[:12]}"),
        session_id=attempt_data.get("session_id", ""),
        quiz_id=attempt_data.get("quiz_id"),
        exam_set_id=attempt_data.get("exam_set_id"),
        max_score=attempt_data.get("max_score", 100),
        learner_id=attempt_data.get("learner_id"),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def get_attempt(db: Session, attempt_id: str) -> AttemptModel | None:
    """Get an attempt by its attempt_id string."""
    return db.query(AttemptModel).filter(
        AttemptModel.attempt_id == attempt_id
    ).first()


def list_attempts(
    db: Session,
    session_id: str = "",
    quiz_id: str = "",
    exam_set_id: str = "",
) -> list[AttemptModel]:
    """List attempts, optionally filtered."""
    q = db.query(AttemptModel)
    if session_id:
        q = q.filter(AttemptModel.session_id == session_id)
    if quiz_id:
        q = q.filter(AttemptModel.quiz_id == quiz_id)
    if exam_set_id:
        q = q.filter(AttemptModel.exam_set_id == exam_set_id)
    return q.order_by(desc(AttemptModel.started_at)).all()


def update_attempt(db: Session, attempt_id: str, data: dict) -> AttemptModel | None:
    """Partial-update an attempt (save progress or submit). Returns updated model."""
    attempt = db.query(AttemptModel).filter(
        AttemptModel.attempt_id == attempt_id
    ).first()
    if attempt is None:
        return None
    if "answers" in data and data["answers"] is not None:
        attempt.answers = data["answers"]
    if "status" in data and data["status"] is not None:
        attempt.status = data["status"]
    if "total_score" in data and data["total_score"] is not None:
        attempt.total_score = data["total_score"]
    if data.get("status") in ("submitted", "graded"):
        attempt.submitted_at = _utcnow()
    db.commit()
    db.refresh(attempt)
    return attempt


def get_attempt_answers(db: Session, attempt_id: str) -> list[AnswerRecordModel]:
    """Get all answer records linked to an attempt."""
    return db.query(AnswerRecordModel).filter(
        AnswerRecordModel.attempt_id == attempt_id
    ).order_by(AnswerRecordModel.created_at).all()


# ── Assessment State (closed-loop persistence) ─────────────────────────

from app.db.models import AssessmentStateModel


def get_assessment_state(db: Session, session_id: str) -> AssessmentStateModel | None:
    """Get the persisted assessment tracking state for a session."""
    return db.get(AssessmentStateModel, session_id)


def upsert_assessment_state(
    db: Session,
    session_id: str,
    *,
    last_diagnosis_at: float | None = None,
    last_mastery_snapshot: dict | None = None,
    events_since_last_diagnosis: int | None = None,
    resource_completions_since_diagnosis: int | None = None,
) -> AssessmentStateModel:
    """Create or update the assessment tracking state for a session."""
    state = db.get(AssessmentStateModel, session_id)
    if state is None:
        state = AssessmentStateModel(session_id=session_id)
        db.add(state)
    if last_diagnosis_at is not None:
        state.last_diagnosis_at = last_diagnosis_at
    if last_mastery_snapshot is not None:
        state.last_mastery_snapshot = last_mastery_snapshot
    if events_since_last_diagnosis is not None:
        state.events_since_last_diagnosis = events_since_last_diagnosis
    if resource_completions_since_diagnosis is not None:
        state.resource_completions_since_diagnosis = resource_completions_since_diagnosis
    db.commit()
    db.refresh(state)
    return state


def get_stale_assessment_sessions(db: Session, stale_seconds: float) -> list[str]:
    """Return session_ids whose last diagnosis is older than *stale_seconds*
    AND that have enough new events to warrant re-assessment."""
    import time
    cutoff = time.time() - stale_seconds
    rows = (
        db.query(AssessmentStateModel.session_id)
        .filter(
            AssessmentStateModel.last_diagnosis_at > 0,
            AssessmentStateModel.last_diagnosis_at < cutoff,
            AssessmentStateModel.events_since_last_diagnosis >= 3,
        )
        .all()
    )
    return [row[0] for row in rows]
