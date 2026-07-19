"""Data access layer for EduAgent persistence.

Each function takes a SQLAlchemy Session and performs one logical operation.
This keeps queries close to the ORM while giving callers control over
transaction boundaries.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import re
from typing import Any
import uuid

from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    AnswerRecordModel,
    AttemptModel,
    DailyTaskModel,
    DiagnosisEvidenceModel,
    DiagnosisSnapshotModel,
    ExamSetModel,
    LearnerModel,
    LearningEventModel,
    LearningPathModel,
    MessageModel,
    PlanningDraftModel,
    PracticeQuestionModel,
    ProfileSnapshotModel,
    QuestionKnowledgePointMappingModel,
    QuizModel,
    ResourceModel,
    SessionModel,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Session ──────────────────────────────────────────────────────────────

_ANONYMOUS_LEARNER_RE = re.compile(
    r"^anon_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _is_session_anonymous(session_learner_id: str | None) -> bool:
    """Return True when the session is currently owned by an anonymous learner."""
    return bool(session_learner_id and _ANONYMOUS_LEARNER_RE.match(str(session_learner_id)))


def try_upgrade_anonymous_session(db: Session, session_id: str, learner_id: str) -> bool:
    """Upgrade an anonymous session to a real learner identity.

    When a session was previously owned by an anonymous learner
    (``anon_<uuid>``) and a real authenticated learner accesses it,
    this function transparently upgrades the session ownership.

    Returns ``True`` if the session was upgraded, ``False`` otherwise.
    Callers should re-query the session after a successful upgrade.
    """
    if not learner_id or _is_session_anonymous(learner_id):
        return False
    sess = db.get(SessionModel, session_id)
    if sess is None:
        return False
    # Upgrade: NULL → real (session created before user logged in)
    if not sess.learner_id:
        sess.learner_id = learner_id
        db.commit()
        return True
    # Upgrade: anonymous (anon_<uuid>) → real (normal login flow)
    if _is_session_anonymous(sess.learner_id):
        sess.learner_id = learner_id
        db.commit()
        return True
    return False


def get_or_create_session(
    db: Session,
    session_id: str,
    learner_id: str | None = None,
    subject_id: str | None = None,
    require_learner: bool = False,
) -> SessionModel:
    sess = db.get(SessionModel, session_id)
    if sess is None:
        if not learner_id:
            logger.info("legacy_session_without_learner_identity")
        sess = SessionModel(
            id=session_id,
            learner_id=get_or_create_learner(db, learner_id).id if learner_id else None,
            subject_id=subject_id or None,
        )
        db.add(sess)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            sess = db.get(SessionModel, session_id)
            if sess is None:
                raise
            return get_or_create_session(db, session_id, learner_id=learner_id, subject_id=subject_id, require_learner=require_learner)
        db.refresh(sess)
    else:
        if require_learner and sess.learner_id and not learner_id:
            raise PermissionError("session requires a learner identity")
        if learner_id:
            if sess.learner_id and sess.learner_id != learner_id:
                # Allow anonymous → real learner transition (normal login flow)
                if _is_session_anonymous(sess.learner_id) and not _is_session_anonymous(learner_id):
                    sess.learner_id = get_or_create_learner(db, learner_id).id
                else:
                    raise PermissionError("session belongs to another learner")
            if not sess.learner_id:
                sess.learner_id = get_or_create_learner(db, learner_id).id
        if subject_id and not sess.subject_id:
            # Backfill subject_id on existing session
            sess.subject_id = subject_id
        if db.is_modified(sess):
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        learner = db.get(LearnerModel, learner_id) if learner_id else None
        if learner is None:
            raise
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


def get_latest_profile_v2_for_subject(db: Session, learner_id: str, subject_id: str) -> dict[str, Any] | None:
    """Return the latest V2 snapshot for one learner and one subject only."""
    if not learner_id or not subject_id:
        return None
    session_ids = [item.id for item in get_learner_sessions(db, learner_id)]
    if not session_ids:
        return None
    snapshots = (
        db.query(ProfileSnapshotModel)
        .filter(ProfileSnapshotModel.session_id.in_(session_ids))
        .order_by(desc(ProfileSnapshotModel.created_at))
        .all()
    )
    for snapshot in snapshots:
        prefs = snapshot.preferences if isinstance(snapshot.preferences, dict) else {}
        profile = prefs.get("profile_v2") if isinstance(prefs.get("profile_v2"), dict) else None
        context = profile.get("subject_context") if isinstance(profile, dict) else {}
        if isinstance(context, dict) and str(context.get("subject_id") or "") == subject_id:
            return profile
    return None


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


# ── User AI Config (per-learner AI credentials) ──────────────────────────


def get_user_ai_config(db: Session, learner_id: str) -> dict[str, Any]:
    """Get the AI credential config JSON blob for a learner, or empty dict."""
    from app.db.models import UserAIConfigModel

    if not learner_id:
        return {}
    row = db.get(UserAIConfigModel, learner_id)
    return row.config if row and isinstance(row.config, dict) else {}


def merge_user_ai_config(
    db: Session, learner_id: str, partial: dict[str, Any]
) -> dict[str, Any]:
    """Merge a partial per-service update into the learner's AI config.

    Semantics (per field inside each service block):
      - value containing ``****`` or ``None`` → ignored (masked placeholder
        echoed back by the frontend must never be persisted);
      - empty string → the field is cleared;
      - anything else → stripped and stored.
    Service blocks left empty after the merge are removed entirely.
    """
    from app.db.models import UserAIConfigModel

    row = db.get(UserAIConfigModel, learner_id)
    if row is None:
        row = UserAIConfigModel(learner_id=learner_id, config={})
        db.add(row)
    current: dict[str, Any] = dict(row.config) if isinstance(row.config, dict) else {}
    for service, fields in (partial or {}).items():
        if not isinstance(fields, dict):
            continue
        block = dict(current.get(service) or {})
        for field, value in fields.items():
            if value is None or "****" in str(value):
                continue  # masked placeholder / no-op
            text = str(value).strip()
            if text == "":
                block.pop(field, None)
            else:
                block[field] = text
        if block:
            current[service] = block
        else:
            current.pop(service, None)
    row.config = current
    db.commit()
    db.refresh(row)
    return row.config


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


def get_latest_cross_session_profile(
    db: Session,
    session_id: str,
) -> ProfileSnapshotModel | None:
    """Get the latest profile_snapshot for the same (learner, subject) across sessions.

    Falls back from the current session to sibling sessions belonging to the
    same learner+subject pair, enabling cross-session profile persistence.
    Returns None when no profile exists for any related session.
    """
    sibling_ids = _sibling_session_ids(db, session_id)
    if sibling_ids is None:
        return get_latest_profile(db, session_id)
    if not sibling_ids:
        return None
    return (
        db.query(ProfileSnapshotModel)
        .filter(ProfileSnapshotModel.session_id.in_(sibling_ids))
        .order_by(desc(ProfileSnapshotModel.created_at))
        .first()
    )


def _sibling_session_ids(
    db: Session, session_id: str
) -> list[str] | None:
    """Collect all session IDs sharing the same (learner, subject) as *session_id*.

    Returns None when the session itself has no learner/subject linkage
    (fall back to session-only lookup). Returns empty list when no sibling
    sessions exist.
    """
    sess = db.get(SessionModel, session_id)
    if not sess or not sess.learner_id or not sess.subject_id:
        return None
    return [
        row[0]
        for row in db.query(SessionModel.id)
        .filter(
            SessionModel.learner_id == sess.learner_id,
            SessionModel.subject_id == sess.subject_id,
        )
        .all()
    ]


def get_cross_session_learning_path(
    db: Session,
    session_id: str,
) -> LearningPathModel | None:
    """Get the latest learning_path for the same (learner, subject) across sessions."""
    sibling_ids = _sibling_session_ids(db, session_id)
    if sibling_ids is None:
        return get_latest_learning_path(db, session_id)
    if not sibling_ids:
        return None
    return (
        db.query(LearningPathModel)
        .filter(LearningPathModel.session_id.in_(sibling_ids))
        .order_by(desc(LearningPathModel.updated_at))
        .first()
    )


def get_cross_session_resources(
    db: Session,
    session_id: str,
) -> list[ResourceModel]:
    """Get all resources for the same (learner, subject) across sessions.

    Returns resources from all sibling sessions, ordered by creation time
    descending. Deduplicates by resource ID.
    """
    sibling_ids = _sibling_session_ids(db, session_id)
    if sibling_ids is None:
        return get_resources(db, session_id)
    if not sibling_ids:
        return []
    seen: set[str] = set()
    results: list[ResourceModel] = []
    for r in (
        db.query(ResourceModel)
        .filter(ResourceModel.session_id.in_(sibling_ids))
        .order_by(desc(ResourceModel.created_at))
        .all()
    ):
        if r.id not in seen:
            seen.add(r.id)
            results.append(r)
    return results


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
        subject_id=path_data.get("subject_id", ""),
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
        existing.subject_id = path.subject_id or existing.subject_id
        existing.course_id = path.course_id
        existing.course_name = path.course_name
        existing.description = path.description
        existing.stages = path.stages
        existing.overall_progress = path.overall_progress
        existing.estimated_days = path.estimated_days
        existing.current_version = path_data.get("current_version", existing.current_version or 0)
        if path_data.get("pending_revision") is not None:
            existing.pending_revision = path_data["pending_revision"]
        if path_data.get("path_revisions") is not None:
            existing.path_revisions = path_data["path_revisions"]
        existing.updated_at = _utcnow()
        path = existing
    else:
        path.current_version = path_data.get("current_version", 0)
        path.pending_revision = path_data.get("pending_revision")
        path.path_revisions = path_data.get("path_revisions")
        db.add(path)
    db.commit()
    db.refresh(path)
    return path


def get_latest_learning_path(db: Session, session_id: str, subject_id: str = "") -> LearningPathModel | None:
    query = db.query(LearningPathModel).filter(LearningPathModel.session_id == session_id)
    if subject_id:
        query = query.filter(
            (LearningPathModel.subject_id == subject_id)
            | ((LearningPathModel.subject_id == "") & LearningPathModel.session.has(subject_id=subject_id))
        )
    return (
        query
        .order_by(desc(LearningPathModel.updated_at))
        .first()
    )


# ── Resources ────────────────────────────────────────────────────────────

def upsert_resource(
    db: Session,
    session_id: str,
    resource_data: dict[str, Any],
) -> ResourceModel:
    session = db.get(SessionModel, session_id)
    get_or_create_session(db, session_id)

    res = ResourceModel(
        id=resource_data.get("id", f"res_{_utcnow().timestamp()}"),
        session_id=session_id,
        learner_id=resource_data.get("learner_id") or resource_data.get("learnerId") or (session.learner_id if session else None),
        subject_id=resource_data.get("subject_id") or resource_data.get("subjectId") or (session.subject_id if session else None),
        path_id=resource_data.get("path_id") or resource_data.get("pathId"),
        generation_version=int(resource_data.get("generation_version") or resource_data.get("generationVersion") or 1),
        supersedes_resource_id=resource_data.get("supersedes_resource_id") or resource_data.get("supersedesResourceId"),
        type=resource_data.get("type", "lecture"),
        title=resource_data.get("title", "学习资源"),
        description=resource_data.get("description"),
        content=resource_data.get("content"),
        knowledge_points=resource_data.get("knowledge_points") or resource_data.get("knowledgePoints"),
        tags=resource_data.get("tags"),
        difficulty=resource_data.get("difficulty", "easy"),
        estimated_minutes=resource_data.get("estimated_minutes") or resource_data.get("estimatedMinutes", 20),
        format=resource_data.get("format", "text"),
        content_format=resource_data.get("content_format") or resource_data.get("contentFormat"),
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
        profile_version=resource_data.get("profile_version") or resource_data.get("profileVersion"),
        diagnosis_version=resource_data.get("diagnosis_version") or resource_data.get("diagnosisVersion"),
        personalization_factors=resource_data.get("personalization_factors") or resource_data.get("personalizationFactors"),
        recommendation_reason=resource_data.get("recommendation_reason") or resource_data.get("recommendationReason") or resource_data.get("reason"),
        quality_status=resource_data.get("quality_status") or resource_data.get("qualityStatus", "passed"),
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
        if res.learner_id:
            existing.learner_id = res.learner_id
        if res.subject_id:
            existing.subject_id = res.subject_id
        if res.path_id:
            existing.path_id = res.path_id
        existing.related_stage_id = res.related_stage_id
        existing.related_chapter_id = res.related_chapter_id
        existing.related_section_id = res.related_section_id
        existing.task_id = res.task_id
        existing.profile_version = res.profile_version
        existing.diagnosis_version = res.diagnosis_version
        existing.personalization_factors = res.personalization_factors
        existing.recommendation_reason = res.recommendation_reason
        existing.quality_status = res.quality_status
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


# ── Quiz Result Events ────────────────────────────────────────────────────


def create_quiz_result_event(
    db: Session,
    *,
    event_id: str,
    session_id: str,
    learner_id: str,
    subject_id: str | None,
    idempotency_key: str,
    attempt_id: str,
    quiz_id: str,
    total_score: int,
    max_score: int,
    normalized_score: float,
    assessment_eligible: bool,
    knowledge_point_results: list[dict],
    path_id: str | None = None,
    stage_id: str | None = None,
    chapter_id: str | None = None,
    section_id: str | None = None,
    occurred_at: str = "",
    schema_version: str = "1.0",
    source: str = "server",
) -> LearningEventModel:
    """Create a canonical quiz_result event (spec §3.6).

    The full structured payload is serialised into ``metadata_`` as a
    ``QuizResultEventDTO``-compatible dict.  The DB-level partial unique
    index on ``(attempt_id) WHERE event_type='quiz_result'`` prevents
    duplicate events for the same attempt.

    Raises ``IntegrityError`` on duplicate (callers should catch and
    treat as a no-op for idempotent replay).
    """
    from datetime import datetime, timezone

    metadata = {
        "eventType": "quiz_result",
        "eventId": event_id,
        "idempotencyKey": idempotency_key,
        "learnerId": learner_id,
        "subjectId": subject_id,
        "sessionId": session_id,
        "pathId": path_id,
        "stageId": stage_id,
        "chapterId": chapter_id,
        "sectionId": section_id,
        "quizId": quiz_id,
        "attemptId": attempt_id,
        "totalScore": total_score,
        "maxScore": max_score,
        "normalizedScore": normalized_score,
        "assessmentEligible": assessment_eligible,
        "knowledgePointResults": knowledge_point_results,
        "occurredAt": occurred_at or datetime.now(timezone.utc).isoformat(),
        "source": source,
        "schemaVersion": schema_version,
    }
    evt = LearningEventModel(
        event_id=event_id,
        session_id=session_id,
        learner_id=learner_id,
        subject_id=subject_id,
        event_type="quiz_result",
        idempotency_key=idempotency_key,
        attempt_id=attempt_id,
        schema_version=schema_version,
        metadata_=metadata,
    )
    db.add(evt)
    return evt


def get_quiz_result_event(
    db: Session, attempt_id: str,
) -> LearningEventModel | None:
    """Return the quiz_result event for *attempt_id*, or None."""
    return (
        db.query(LearningEventModel)
        .filter(
            LearningEventModel.attempt_id == attempt_id,
            LearningEventModel.event_type == "quiz_result",
        )
        .first()
    )


def check_quiz_result_event_exists(db: Session, attempt_id: str) -> bool:
    """Return True if a quiz_result event already exists for *attempt_id*."""
    return (
        db.query(LearningEventModel)
        .filter(
            LearningEventModel.attempt_id == attempt_id,
            LearningEventModel.event_type == "quiz_result",
        )
        .first()
        is not None
    )


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


def _event_in_analytics_scope(
    event: LearningEventModel,
    *,
    subject_id: str = "",
    path_id: str = "",
    stage_id: str = "",
    include_legacy_unscoped: bool = False,
) -> bool:
    """Keep legacy metadata events readable without mixing explicit scopes."""
    metadata = event.metadata_ or {}
    event_subject = str(event.subject_id or metadata.get("subjectId") or metadata.get("subject_id") or "")
    if subject_id and event_subject != subject_id:
        if not (include_legacy_unscoped and not event_subject):
            return False
    if path_id and str(metadata.get("pathId") or metadata.get("path_id") or "") != path_id:
        return False
    if stage_id and str(metadata.get("stageId") or metadata.get("stage_id") or "") != stage_id:
        return False
    return True


def get_scoped_events(
    db: Session,
    session_id: str,
    *,
    subject_id: str = "",
    path_id: str = "",
    stage_id: str = "",
    include_legacy_unscoped: bool = False,
) -> list[LearningEventModel]:
    return [
        event for event in get_events(db, session_id)
        if _event_in_analytics_scope(
            event,
            subject_id=subject_id,
            path_id=path_id,
            stage_id=stage_id,
            include_legacy_unscoped=include_legacy_unscoped,
        )
    ]


def _normalized_score(total_score: Any, max_score: Any) -> int | None:
    try:
        maximum = float(max_score)
        return round(float(total_score) * 100 / maximum) if maximum > 0 else None
    except (TypeError, ValueError):
        return None


def get_assessment_metrics(
    db: Session, session_id: str, subject_id: str, events: list[LearningEventModel],
) -> dict[str, Any]:
    """Use completed attempts as the authoritative assessment metric source."""
    attempts = db.query(AttemptModel).filter(
        AttemptModel.session_id == session_id,
        AttemptModel.status.in_(("graded", "completed")),
    )
    if subject_id:
        attempts = attempts.filter((AttemptModel.subject_id == subject_id) | AttemptModel.subject_id.is_(None))
    attempts = attempts.order_by(AttemptModel.submitted_at, AttemptModel.attempt_id).all()
    attempt_ids = {attempt.attempt_id for attempt in attempts}
    outcomes: list[dict[str, Any]] = []
    answered = correct = 0

    for attempt in attempts:
        records = db.query(AnswerRecordModel).filter(AnswerRecordModel.attempt_id == attempt.attempt_id).all()
        if records:
            response_count = sum(bool(str(record.student_answer or "").strip()) for record in records)
            correct_count = sum(bool(record.total_score and record.total_score > 0) for record in records)
        else:
            answers = attempt.answers if isinstance(attempt.answers, list) else []
            response_count = sum(bool(str(item.get("answer") or item.get("student_answer") or "").strip()) for item in answers if isinstance(item, dict))
            correct_count = sum(bool(item.get("score", 0)) for item in answers if isinstance(item, dict))
        score = _normalized_score(attempt.total_score, attempt.max_score)
        answered += response_count
        correct += correct_count
        outcomes.append({
            "attemptId": attempt.attempt_id, "date": (attempt.submitted_at or attempt.graded_at or attempt.created_at).strftime("%Y-%m-%d"),
            "timestamp": (attempt.submitted_at or attempt.graded_at or attempt.created_at).isoformat(),
            "accuracy": score, "answeredCount": response_count, "correctCount": correct_count, "source": "attempt",
        })

    seen_legacy: set[str] = set()
    for event in events:
        meta = event.metadata_ or {}
        legacy_attempt_id = str(event.attempt_id or meta.get("attemptId") or "")
        if event.event_type not in {"quiz_result", "quiz_submit", "practice_result"} or legacy_attempt_id in attempt_ids:
            continue
        key = legacy_attempt_id or str(event.event_id)
        if key in seen_legacy:
            continue
        try:
            total = int(meta.get("totalQuestions", meta.get("total", 0)) or 0)
            right = int(meta.get("correct", 0) or 0)
        except (TypeError, ValueError):
            total = right = 0
        score = meta.get("normalizedScore", meta.get("accuracy", meta.get("score")))
        try:
            score = round(float(score) * 100) if float(score) <= 1 else round(float(score))
        except (TypeError, ValueError):
            score = _normalized_score(right, total)
        if total <= 0:
            continue
        seen_legacy.add(key)
        answered += total
        correct += right
        outcomes.append({"attemptId": legacy_attempt_id or key, "date": event.created_at.strftime("%Y-%m-%d"), "timestamp": event.created_at.isoformat(), "accuracy": score, "answeredCount": total, "correctCount": right, "source": "legacy_event"})

    outcomes.sort(key=lambda item: item["timestamp"])
    accuracy = round(correct * 100 / answered) if answered else None
    score_outcomes = [item for item in outcomes if item["accuracy"] is not None]
    detail = lambda value, count, source: {"value": value, "status": "available" if value is not None else "insufficient_data", "sampleCount": count, "source": source, "updatedAt": outcomes[-1]["timestamp"] if outcomes else None}
    return {
        "assessmentCount": len(attempts), "questionAnsweredCount": answered, "correctQuestionCount": correct,
        "quizAccuracy": accuracy, "latestQuizScore": score_outcomes[-1] if score_outcomes else None,
        "bestQuizScore": max(score_outcomes, key=lambda item: item["accuracy"]) if score_outcomes else None,
        "quizTrend": outcomes[-30:], "scoreTrend": outcomes[-30:], "practiceCount": len(attempts),
        "metricDetails": {
            "assessmentCount": detail(len(attempts) if attempts else None, len(attempts), "attempt"),
            "questionAnsweredCount": detail(answered if outcomes else None, answered, "attempt" if attempts else "legacy_event"),
            "correctQuestionCount": detail(correct if outcomes else None, answered, "attempt" if attempts else "legacy_event"),
            "accuracy": detail(accuracy, answered, "attempt" if attempts else "legacy_event"),
        },
    }


def get_event_analytics(
    db: Session,
    session_id: str,
    *,
    subject_id: str = "",
    path_id: str = "",
    stage_id: str = "",
    include_legacy_unscoped: bool = False,
) -> dict[str, Any]:
    """Compute analytics summary from learning events (mirrors LearningTracker.summary)."""
    events = get_scoped_events(
        db, session_id, subject_id=subject_id, path_id=path_id,
        stage_id=stage_id, include_legacy_unscoped=include_legacy_unscoped,
    )
    assessment_metrics = get_assessment_metrics(db, session_id, subject_id, events)

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
            # ── Structured format (commit 3+ server-authoritative events) ──
            if meta.get("eventType") == "quiz_result":
                try:
                    ts = int(meta.get("totalScore", 0))
                    ms = int(meta.get("maxScore", 100))
                    ns = float(meta.get("normalizedScore", 0))
                    quiz_scores.append(round(ns * 100))
                    quiz_correct += max(0, ts)
                    quiz_total += ms
                    quiz_pct = round(ns * 100)
                    quiz_results.append({
                        "score": quiz_pct,
                        "topic": "",
                        "timestamp": evt.created_at.isoformat() if evt.created_at else "",
                    })
                except (TypeError, ValueError):
                    pass
            else:
                # ── Legacy format (frontend-logged events) ──
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
                quiz_pct2: float | None = None
                if "accuracy" in meta:
                    try:
                        a = float(meta["accuracy"])
                        quiz_pct2 = round(a * 100) if a <= 1 else round(a)
                    except (TypeError, ValueError):
                        pass
                if quiz_pct2 is None and "score" in meta:
                    try:
                        s = float(meta["score"])
                        quiz_pct2 = round(s * 100) if s <= 1 else round(s)
                    except (TypeError, ValueError):
                        pass
                if quiz_pct2 is None and "correct" in meta and "total" in meta:
                    try:
                        c = int(meta["correct"])
                        t = int(meta["total"])
                        if t > 0:
                            quiz_pct2 = round(c / t * 100)
                    except (TypeError, ValueError):
                        pass
                if quiz_pct2 is not None:
                    quiz_results.append({
                        "score": quiz_pct2,
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
        if meta.get("eventType") == "quiz_result":
            # ── Structured format: iterate knowledgePointResults ──
            kprs = meta.get("knowledgePointResults") or []
            for kpr in (kprs if isinstance(kprs, list) else []):
                if not isinstance(kpr, dict):
                    continue
                kp_key = str(kpr.get("knowledgePointKey") or kpr.get("knowledgePointLabel") or "")
                if not kp_key:
                    continue
                topic_total[kp_key] = topic_total.get(kp_key, 0) + 1
                if not kpr.get("isCorrect", True):
                    topic_wrong[kp_key] = topic_wrong.get(kp_key, 0) + 1
        else:
            # ── Legacy format ──
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
        if meta.get("eventType") == "quiz_result":
            # ── Structured format ──
            kprs = meta.get("knowledgePointResults") or []
            for kpr in (kprs if isinstance(kprs, list) else []):
                if not isinstance(kpr, dict):
                    continue
                tk = str(kpr.get("knowledgePointKey") or kpr.get("knowledgePointLabel") or "")
                if not tk:
                    continue
                if tk not in topic_sources:
                    topic_sources[tk] = set()
                topic_sources[tk].add("quiz")
        else:
            # ── Legacy format ──
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
            "sampleCount": topic_total.get(topic, 1),
            "status": "available" if topic_total.get(topic, 1) >= 3 else "insufficient_data",
            "priority": "high" if topic_total.get(topic, 1) >= 3 and wrong / max(1, topic_total.get(topic, 1)) > 0.5 else "medium",
        }
        for topic, wrong in ranked[:5]
        if wrong > 0
    ]

    # ── Structured recommendations from 5 sources ──
    try:
        session_resources = get_resources(db, session_id)
        if stage_id:
            session_resources = [r for r in session_resources if r.related_stage_id == stage_id]
    except SQLAlchemyError:
        session_resources = []

    try:
        session_path = (
            db.query(LearningPathModel).filter(LearningPathModel.id == path_id).first()
            if path_id else get_latest_learning_path(db, session_id)
        )
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
    regularity_score: int | None = None
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
    if regularity_score is not None and regularity_score >= 70:
        assessment_parts.append("学习规律性强")
    elif regularity_score is not None and regularity_score <= 30 and len(active_days) >= 3:
        assessment_parts.append("学习间隔不规律，建议固定每天的学习时间")
    if weak_topics:
        topics_str = "、".join([w["topic"] for w in weak_topics[:3]])
        assessment_parts.append(f"重点关注：{topics_str}")
    assessment_summary = "。".join(assessment_parts) + "。" if assessment_parts else "暂无足够数据生成评估。"

    return {
        "eventCount": len(events),
        "totalStudyMinutes": total_minutes,
        "trackedStudyDuration": total_minutes,
        "durationDataQuality": {"value": total_minutes, "status": "available" if total_minutes else "insufficient_data", "sampleCount": sum(1 for event in events if (event.metadata_ or {}).get("duration") or (event.metadata_ or {}).get("durationMinutes")), "source": "learning_events", "updatedAt": None},
        "timezoneUsed": "UTC",
        "todayStudyMinutes": today_study_minutes,
        "streak": streak,
        "activeResourceCount": len(resource_counts),
        "modeMetrics": mode_metrics if mode_metrics else None,
        "viewedResources": event_counts.get("resource_view", 0),
        "completedResources": event_counts.get("resource_complete", 0),
        **assessment_metrics,
        "resourceViewCount": event_counts.get("resource_view", 0),
        "resourceCompleteCount": event_counts.get("resource_complete", 0),
        "lastStudyTime": int(last_study_ts * 1000) if last_study_ts else None,
        "eventBreakdown": event_counts,
        "topResources": [
            {"resourceId": rid, "count": cnt, "title": resource_titles.get(rid, "")} for rid, cnt in top_resources
        ],
        "weakTopics": weak_topics,
        "recommendations": recommendations,
        "completionTrend": completion_trend,
        "quizTrend": assessment_metrics["quizTrend"],
        # Quiz latest/best for explicit clarity (requirement: "latest / best 要清楚")
        "latestQuizScore": assessment_metrics["latestQuizScore"],
        "bestQuizScore": assessment_metrics["bestQuizScore"],
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
        "regularityMetric": {"value": regularity_score, "status": "available" if regularity_score is not None else "insufficient_data", "sampleCount": len(active_days), "source": "learning_events", "updatedAt": None},
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
        subject_id=attempt_data.get("subject_id"),
        path_id=attempt_data.get("path_id"),
        stage_id=attempt_data.get("stage_id"),
        task_id=attempt_data.get("task_id"),
        quiz_id=attempt_data.get("quiz_id"),
        exam_set_id=attempt_data.get("exam_set_id"),
        max_score=attempt_data.get("max_score", 100),
        learner_id=attempt_data.get("learner_id"),
        idempotency_key=attempt_data.get("idempotency_key"),
        attempt_number=attempt_data.get("attempt_number", 1),
        assessment_eligible=attempt_data.get("assessment_eligible", True),
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
    if data.get("status") in ("submitted", "graded", "processing", "completed"):
        if attempt.submitted_at is None:
            attempt.submitted_at = _utcnow()
    if data.get("status") in ("graded", "processing", "completed"):
        attempt.graded_at = data.get("graded_at", _utcnow())
    if "assessment_eligible" in data:
        attempt.assessment_eligible = data["assessment_eligible"]
    if "processing_task_id" in data:
        attempt.processing_task_id = data["processing_task_id"]
    if "diagnosis_task_id" in data:
        attempt.diagnosis_task_id = data["diagnosis_task_id"]
    db.commit()
    db.refresh(attempt)
    return attempt


def get_attempt_answers(db: Session, attempt_id: str) -> list[AnswerRecordModel]:
    """Get all answer records linked to an attempt."""
    return db.query(AnswerRecordModel).filter(
        AnswerRecordModel.attempt_id == attempt_id
    ).order_by(AnswerRecordModel.created_at).all()


def find_attempt_by_idempotency_key(
    db: Session,
    learner_id: str,
    idempotency_key: str,
    *,
    quiz_id: str | None = None,
    exam_set_id: str | None = None,
) -> AttemptModel | None:
    """Look up an existing attempt by its idempotency key and parent resource."""
    q = db.query(AttemptModel).filter(
        AttemptModel.learner_id == learner_id,
        AttemptModel.idempotency_key == idempotency_key,
    )
    if quiz_id:
        q = q.filter(AttemptModel.quiz_id == quiz_id)
    if exam_set_id:
        q = q.filter(AttemptModel.exam_set_id == exam_set_id)
    return q.order_by(desc(AttemptModel.created_at)).first()


def get_next_attempt_number(
    db: Session,
    learner_id: str,
    *,
    quiz_id: str | None = None,
    exam_set_id: str | None = None,
) -> int:
    """Compute the next attempt_number for a learner on a quiz or exam set."""
    q = db.query(func.count(AttemptModel.id)).filter(
        AttemptModel.learner_id == learner_id,
    )
    if quiz_id:
        q = q.filter(AttemptModel.quiz_id == quiz_id)
    if exam_set_id:
        q = q.filter(AttemptModel.exam_set_id == exam_set_id)
    return (q.scalar() or 0) + 1


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


# ── Planning Drafts ───────────────────────────────────────────────────────


def upsert_planning_draft(
    db: Session,
    draft_id: str,
    learner_id: str,
    session_id: str,
    subject_id: str = "",
    **fields,
) -> PlanningDraftModel:
    """Create or update a planning draft."""
    sess = get_or_create_session(db, session_id, learner_id=learner_id, subject_id=subject_id)
    draft = db.get(PlanningDraftModel, draft_id)
    if draft is None:
        draft = PlanningDraftModel(
            id=draft_id,
            learner_id=learner_id,
            session_id=session_id,
            subject_id=subject_id,
        )
        db.add(draft)
    for key in ("topic", "goal", "current_level", "daily_time", "target_duration", "status"):
        if key in fields and fields[key] is not None:
            setattr(draft, key, fields[key])
    if "resource_preferences" in fields:
        draft.resource_preferences = fields["resource_preferences"]
    db.commit()
    db.refresh(draft)
    return draft


def get_planning_draft(db: Session, draft_id: str) -> PlanningDraftModel | None:
    """Get a single planning draft by ID."""
    return db.get(PlanningDraftModel, draft_id)


def get_planning_draft_by_session(
    db: Session, session_id: str, subject_id: str = ""
) -> PlanningDraftModel | None:
    """Get the latest planning draft for a session."""
    return (
        db.query(PlanningDraftModel)
        .filter(PlanningDraftModel.session_id == session_id)
        .filter(PlanningDraftModel.subject_id == subject_id)
        .order_by(PlanningDraftModel.updated_at.desc())
        .first()
    )


def get_planning_drafts_for_learner(
    db: Session, learner_id: str
) -> list[PlanningDraftModel]:
    """Get all planning drafts for a learner."""
    return (
        db.query(PlanningDraftModel)
        .filter(PlanningDraftModel.learner_id == learner_id)
        .order_by(PlanningDraftModel.updated_at.desc())
        .all()
    )


def delete_planning_draft(db: Session, draft_id: str) -> bool:
    """Delete a planning draft by ID. Returns True if deleted."""
    draft = db.get(PlanningDraftModel, draft_id)
    if draft is None:
        return False
    db.delete(draft)
    db.commit()
    return True


# ── Question–Knowledge Point Mappings ──────────────────────────────────────


def get_mappings_for_question(
    db: Session, question_id: str,
) -> list[QuestionKnowledgePointMappingModel]:
    """Get all KP mappings for a question, ordered by weight descending."""
    return (
        db.query(QuestionKnowledgePointMappingModel)
        .filter(QuestionKnowledgePointMappingModel.question_id == question_id)
        .order_by(QuestionKnowledgePointMappingModel.weight.desc())
        .all()
    )


def get_mappings_for_questions(
    db: Session, question_ids: list[str],
) -> dict[str, list[QuestionKnowledgePointMappingModel]]:
    """Batch lookup: question_id → list of mappings."""
    if not question_ids:
        return {}
    rows = (
        db.query(QuestionKnowledgePointMappingModel)
        .filter(QuestionKnowledgePointMappingModel.question_id.in_(question_ids))
        .order_by(QuestionKnowledgePointMappingModel.weight.desc())
        .all()
    )
    result: dict[str, list[QuestionKnowledgePointMappingModel]] = {qid: [] for qid in question_ids}
    for row in rows:
        result.setdefault(row.question_id, []).append(row)
    return result


def create_question_kp_mapping(
    db: Session,
    *,
    mapping_id: str,
    question_id: str,
    knowledge_point_key: str,
    knowledge_point_label: str = "",
    weight: float = 1.0,
    confidence: float = 1.0,
    source: str = "explicit",
    subject_id: str | None = None,
    mapping_version: int = 1,
) -> QuestionKnowledgePointMappingModel:
    """Create a single question→knowledge-point mapping."""
    mapping = QuestionKnowledgePointMappingModel(
        mapping_id=mapping_id,
        question_id=question_id,
        subject_id=subject_id,
        knowledge_point_key=knowledge_point_key,
        knowledge_point_label=knowledge_point_label or knowledge_point_key,
        weight=weight,
        confidence=confidence,
        source=source,
        mapping_version=mapping_version,
    )
    db.add(mapping)
    return mapping


def get_or_create_fallback_mappings(
    db: Session,
    question_id: str,
    subject_id: str | None,
    kp_strings: list[str],
) -> list[QuestionKnowledgePointMappingModel]:
    """Create equal-weight fallback mappings from old string-list knowledge_points.

    Only creates new mappings if no rows exist for this question yet.
    Returns existing mappings if they already exist.
    """
    if not kp_strings:
        return []

    weight = 1.0 / len(kp_strings)
    mappings: list[QuestionKnowledgePointMappingModel] = []
    for kp_str in dict.fromkeys(kp_strings):
        kp_str = kp_str.strip()
        if not kp_str:
            continue
        query = db.query(QuestionKnowledgePointMappingModel).filter(
            QuestionKnowledgePointMappingModel.question_id == question_id,
            QuestionKnowledgePointMappingModel.knowledge_point_key == kp_str,
            QuestionKnowledgePointMappingModel.subject_id.is_(None) if subject_id is None else QuestionKnowledgePointMappingModel.subject_id == subject_id,
        )
        m = query.first()
        if m:
            mappings.append(m)
            continue
        # 3 + 48 hex = 51 chars; deterministic across retries and never loses a long-ID suffix.
        mapping_id = "fb_" + hashlib.sha256(f"{subject_id or ''}\x1f{question_id}\x1f{kp_str}\x1f1".encode()).hexdigest()[:48]
        try:
            with db.begin_nested():
                m = create_question_kp_mapping(
                    db, mapping_id=mapping_id, question_id=question_id, knowledge_point_key=kp_str,
                    knowledge_point_label=kp_str, weight=weight, confidence=0.5, source="fallback",
                    subject_id=subject_id, mapping_version=1,
                )
                db.flush()
        except IntegrityError:
            m = query.first()
            if not m:
                raise
        mappings.append(m)
    return mappings


def ensure_question_kp_mappings(
    db: Session,
    question: PracticeQuestionModel,
    subject_id: str | None = None,
) -> list[QuestionKnowledgePointMappingModel]:
    """Resolve KP mappings for a question, creating fallbacks from legacy data.

    Priority:
    1. Existing explicit / generated / fallback mappings in DB
    2. Create fallback from question.knowledge_points (JSON string list)
    3. Return empty list when nothing is available (unmapped)
    """
    existing = get_mappings_for_question(db, question.question_id)
    if existing:
        return existing

    # Try to create fallback mappings from legacy knowledge_points JSON
    raw_kps: list[str] = []
    kp_data = question.knowledge_points
    if isinstance(kp_data, list):
        raw_kps = [str(k) for k in kp_data if k and str(k).strip()]
    elif isinstance(kp_data, dict):
        # Handle dict form: {"name": "..."} or {"kp_name": ...}
        raw_kps = [str(v) for v in kp_data.values() if v and str(v).strip()]

    if raw_kps:
        mappings = get_or_create_fallback_mappings(
            db, question.question_id, subject_id, raw_kps,
        )
        if mappings:
            return mappings

    # Unmapped — no knowledge point data available
    return []


# ── Diagnosis Snapshots & Evidence (spec §4.1–4.2) ────────────────────────


def get_next_diagnosis_version(
    db: Session, learner_id: str, subject_id: str,
) -> int:
    """Return the next version number for a (learner, subject) pair."""
    max_ver = (
        db.query(func.max(DiagnosisSnapshotModel.version))
        .filter(
            DiagnosisSnapshotModel.learner_id == learner_id,
            DiagnosisSnapshotModel.subject_id == subject_id,
        )
        .scalar()
    )
    return (max_ver or 0) + 1


def supersede_snapshots(
    db: Session, learner_id: str, subject_id: str, *,
    except_snapshot_id: str = "",
) -> int:
    """Mark all ready snapshots as superseded except the given one.

    Returns the number of rows updated.
    """
    filters = [
        DiagnosisSnapshotModel.learner_id == learner_id,
        DiagnosisSnapshotModel.subject_id == subject_id,
        DiagnosisSnapshotModel.status.in_(["ready", "generating"]),
    ]
    if except_snapshot_id:
        filters.append(DiagnosisSnapshotModel.diagnosis_snapshot_id != except_snapshot_id)
    count = (
        db.query(DiagnosisSnapshotModel)
        .filter(*filters)
        .update({"status": "superseded"}, synchronize_session=False)
    )
    return count


def create_diagnosis_snapshot(
    db: Session,
    *,
    diagnosis_snapshot_id: str,
    learner_id: str,
    subject_id: str | None,
    session_id: str,
    version: int,
    status: str = "ready",
    mastery_levels: list | None = None,
    weaknesses: list | None = None,
    strengths: list | None = None,
    confidence: float | None = None,
    summary: str | None = None,
    source_attempt_ids: list | None = None,
    source_event_ids: list | None = None,
    evidence_count: int = 0,
    generated_by: str = "diagnosis_agent",
    supersedes_snapshot_id: str | None = None,
    active_task_id: str | None = None,
) -> DiagnosisSnapshotModel:
    """Create a new diagnosis snapshot row."""
    snap = DiagnosisSnapshotModel(
        diagnosis_snapshot_id=diagnosis_snapshot_id,
        learner_id=learner_id,
        subject_id=subject_id or "",
        session_id=session_id,
        version=version,
        status=status,
        mastery_levels=mastery_levels or [],
        weaknesses=weaknesses or [],
        strengths=strengths or [],
        confidence=confidence,
        summary=summary,
        source_attempt_ids=source_attempt_ids or [],
        source_event_ids=source_event_ids or [],
        evidence_count=evidence_count,
        generated_by=generated_by,
        supersedes_snapshot_id=supersedes_snapshot_id,
        active_task_id=active_task_id,
    )
    db.add(snap)
    db.flush()
    return snap


def get_latest_diagnosis_snapshot(
    db: Session, learner_id: str, subject_id: str,
) -> DiagnosisSnapshotModel | None:
    """Return the latest ready snapshot for a (learner, subject) pair."""
    return (
        db.query(DiagnosisSnapshotModel)
        .filter(
            DiagnosisSnapshotModel.learner_id == learner_id,
            DiagnosisSnapshotModel.subject_id == subject_id,
            DiagnosisSnapshotModel.status == "ready",
        )
        .order_by(DiagnosisSnapshotModel.version.desc())
        .first()
    )


def get_diagnosis_at_version(
    db: Session, learner_id: str, subject_id: str, version: int,
) -> DiagnosisSnapshotModel | None:
    """Return a specific version of a diagnosis snapshot."""
    return (
        db.query(DiagnosisSnapshotModel)
        .filter(
            DiagnosisSnapshotModel.learner_id == learner_id,
            DiagnosisSnapshotModel.subject_id == subject_id,
            DiagnosisSnapshotModel.version == version,
        )
        .first()
    )


def create_diagnosis_evidence(
    db: Session,
    *,
    evidence_id: str,
    diagnosis_snapshot_id: str,
    learner_id: str,
    knowledge_point_key: str,
    evidence_type: str = "quiz_answer",
    subject_id: str | None = None,
    attempt_id: str | None = None,
    question_id: str | None = None,
    learning_event_id: str | None = None,
    resource_id: str | None = None,
    score: float | None = None,
    weight: float | None = None,
    confidence: float | None = None,
    occurred_at: datetime | None = None,
    metadata_: dict | None = None,
) -> DiagnosisEvidenceModel:
    """Create a single evidence row linked to a diagnosis snapshot."""
    ev = DiagnosisEvidenceModel(
        evidence_id=evidence_id,
        diagnosis_snapshot_id=diagnosis_snapshot_id,
        learner_id=learner_id,
        subject_id=subject_id,
        knowledge_point_key=knowledge_point_key,
        evidence_type=evidence_type,
        attempt_id=attempt_id,
        question_id=question_id,
        learning_event_id=learning_event_id,
        resource_id=resource_id,
        score=score,
        weight=weight,
        confidence=confidence,
        occurred_at=occurred_at or _utcnow(),
        metadata_=metadata_,
    )
    db.add(ev)
    return ev


def get_evidence_for_snapshot(
    db: Session, diagnosis_snapshot_id: str,
) -> list[DiagnosisEvidenceModel]:
    """Return all evidence rows for a given snapshot."""
    return (
        db.query(DiagnosisEvidenceModel)
        .filter(DiagnosisEvidenceModel.diagnosis_snapshot_id == diagnosis_snapshot_id)
        .order_by(DiagnosisEvidenceModel.knowledge_point_key)
        .all()
    )


def collect_evidence_from_events(
    db: Session,
    learner_id: str,
    subject_id: str | None,
    source_event_ids: list[str],
    source_attempt_ids: list[str],
) -> list[dict]:
    """Collect structured evidence records from quiz_result events and answer records.

    Each entry is a dict suitable for passing to ``create_diagnosis_evidence``.
    Evidence is only collected for ``assessment_eligible`` attempts.
    """
    evidence: list[dict] = []

    # ── From quiz_result events ─────────────────────────────────
    if source_event_ids:
        events = (
            db.query(LearningEventModel)
            .filter(LearningEventModel.event_id.in_(source_event_ids))
            .all()
        )
        for evt in events:
            meta = evt.metadata_ or {}
            kprs = meta.get("knowledgePointResults", [])
            if isinstance(kprs, list):
                for kpr in kprs:
                    if not kpr.get("assessmentEligible", True):
                        continue
                    evidence.append({
                        "knowledge_point_key": str(kpr.get("knowledgePointKey", "")),
                        "evidence_type": "quiz_answer",
                        "attempt_id": evt.attempt_id,
                        "question_id": str(kpr.get("questionId", "")),
                        "learning_event_id": evt.event_id,
                        "score": float(kpr.get("normalizedScore", 0)),
                        "weight": float(kpr.get("weight", 1.0)),
                        "confidence": float(kpr.get("mappingConfidence", 1.0)),
                        "occurred_at": evt.created_at,
                        "metadata_": kpr,
                    })

    # ── From legacy AnswerRecords (no quiz_result event yet) ───
    if source_attempt_ids:
        # Only include attempts that don't already have a quiz_result event
        attempts_with_events = set()
        if source_event_ids:
            evt_attempts = (
                db.query(LearningEventModel.attempt_id)
                .filter(LearningEventModel.event_id.in_(source_event_ids))
                .all()
            )
            attempts_with_events = {a[0] for a in evt_attempts if a[0]}

        for aid in source_attempt_ids:
            if aid in attempts_with_events:
                continue
            # Check assessment_eligible
            attempt = db.get(AttemptModel, aid) if hasattr(AttemptModel, 'attempt_id') else None
            if attempt is None:
                att = db.query(AttemptModel).filter(AttemptModel.attempt_id == aid).first()
                if att is None or not getattr(att, "assessment_eligible", True):
                    continue
                attempt_id_val = att.attempt_id
            else:
                attempt_id_val = aid

            answer_records = (
                db.query(AnswerRecordModel)
                .filter(AnswerRecordModel.attempt_id == attempt_id_val)
                .all()
            )
            for ar in answer_records:
                q_score = float(ar.total_score or 0)
                evidence.append({
                    "knowledge_point_key": f"question_{ar.question_id}",
                    "evidence_type": "quiz_answer",
                    "attempt_id": attempt_id_val,
                    "question_id": ar.question_id,
                    "score": q_score / 100.0,
                    "weight": 1.0,
                    "confidence": 0.8,
                    "occurred_at": ar.created_at,
                    "metadata_": {
                        "errorType": ar.error_type,
                        "totalScore": ar.total_score,
                    },
                })

    return evidence
