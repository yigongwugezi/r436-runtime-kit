"""Data access layer for EduAgent persistence.

Each function takes a SQLAlchemy Session and performs one logical operation.
This keeps queries close to the ORM while giving callers control over
transaction boundaries.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.models import (
    LearningEventModel,
    LearningPathModel,
    MessageModel,
    ProfileSnapshotModel,
    ResourceModel,
    SessionModel,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Session ──────────────────────────────────────────────────────────────

def get_or_create_session(db: Session, session_id: str) -> SessionModel:
    sess = db.get(SessionModel, session_id)
    if sess is None:
        sess = SessionModel(id=session_id)
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return sess


def list_sessions(db: Session, status: str = "active") -> list[SessionModel]:
    return (
        db.query(SessionModel)
        .filter(SessionModel.status == status)
        .order_by(desc(SessionModel.updated_at))
        .all()
    )


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

def save_learning_path(
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
        stages=path_data.get("stages"),
        overall_progress=path_data.get("overallProgress", 0),
        estimated_days=path_data.get("estimatedDays", 14),
    )
    # Merge existing if same id
    existing = db.get(LearningPathModel, path.id)
    if existing:
        existing.course_id = path.course_id
        existing.course_name = path.course_name
        existing.stages = path.stages
        existing.overall_progress = path.overall_progress
        existing.estimated_days = path.estimated_days
        existing.updated_at = _utcnow()
    else:
        db.add(path)
    db.commit()
    return path


def get_latest_learning_path(db: Session, session_id: str) -> LearningPathModel | None:
    return (
        db.query(LearningPathModel)
        .filter(LearningPathModel.session_id == session_id)
        .order_by(desc(LearningPathModel.updated_at))
        .first()
    )


# ── Resources ────────────────────────────────────────────────────────────

def save_resource(
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
        tags=resource_data.get("tags"),
        bookmarked=resource_data.get("bookmarked", False),
    )
    existing = db.get(ResourceModel, res.id)
    if existing:
        existing.type = res.type
        existing.title = res.title
        existing.description = res.description
        existing.content = res.content
        existing.tags = res.tags
        existing.bookmarked = res.bookmarked
    else:
        db.add(res)
    db.commit()
    return res


def get_resources(db: Session, session_id: str) -> list[ResourceModel]:
    return (
        db.query(ResourceModel)
        .filter(ResourceModel.session_id == session_id)
        .order_by(desc(ResourceModel.created_at))
        .all()
    )


def get_resource(db: Session, resource_id: str) -> ResourceModel | None:
    return db.get(ResourceModel, resource_id)


def toggle_bookmark(db: Session, resource_id: str) -> bool | None:
    res = db.get(ResourceModel, resource_id)
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


# ── Learning Events ──────────────────────────────────────────────────────

def log_event(
    db: Session,
    session_id: str,
    event_type: str,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> LearningEventModel:
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
    q = db.query(LearningEventModel)
    if session_id:
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
    topic_wrong: dict[str, int] = {}
    topic_total: dict[str, int] = {}

    for evt in events:
        meta = evt.metadata_ or {}
        # Duration
        duration = meta.get("duration") or meta.get("durationMinutes") or 0
        try:
            total_minutes += max(0, int(duration))
        except (TypeError, ValueError):
            pass

        # Resource counter
        if evt.resource_id:
            resource_counts[evt.resource_id] = resource_counts.get(evt.resource_id, 0) + 1

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

    # Weak topics
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
        }
        for topic, wrong in ranked[:5]
        if wrong > 0
    ]

    # Recommendations
    recommendations: list[str] = []
    if total_minutes < 30:
        recommendations.append("学习时长还偏少，建议先完成一个核心讲义和一组基础练习。")
    if quiz_accuracy is not None and quiz_accuracy < 70:
        recommendations.append("练习正确率偏低，建议降低资源难度并增加图解讲解。")
    if weak_topics:
        recommendations.append(f"优先复习薄弱知识点：{weak_topics[0]['topic']}。")
    if not recommendations:
        recommendations.append("当前学习节奏稳定，可以继续推进下一阶段任务。")

    top_resources = sorted(resource_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "eventCount": len(events),
        "totalStudyMinutes": total_minutes,
        "activeResourceCount": len(resource_counts),
        "eventBreakdown": event_counts,
        "topResources": [
            {"resourceId": rid, "count": cnt} for rid, cnt in top_resources
        ],
        "quizAccuracy": quiz_accuracy,
        "weakTopics": weak_topics,
        "recommendations": recommendations,
        "recentEvents": [
            {
                "event": evt.event_type,
                "resourceId": evt.resource_id,
                "metadata": evt.metadata_,
                "timestamp": evt.created_at.isoformat() if evt.created_at else None,
            }
            for evt in events[-10:]
        ],
    }
