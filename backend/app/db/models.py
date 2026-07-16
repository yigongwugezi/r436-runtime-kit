"""SQLAlchemy ORM models for EduAgent persistence.

Design notes:
- session_id is the primary access key; learner_id links sessions to a learner.
- learner_id is nullable for backward compatibility with pre-Learner sessions.
- JSON columns use SQLAlchemy's JSON type (TEXT in SQLite, JSONB in PostgreSQL).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Learner ───────────────────────────────────────────────────────────────

class LearnerModel(Base):
    """A learner (user) who can have multiple learning sessions.

    Each learner aggregates learning portraits across sessions, enabling
    cross-session profile tracking and personalization.

    Role system: student (default), parent, teacher, admin.
    Parents can link to children via parent_id on the child's record.
    """

    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(128), default="学习者")

    # ── Auth ─────────────────────────────────────────────────────────
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, default=None, index=True
    )
    wechat_openid: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, default=None
    )
    student_no: Mapped[str | None] = mapped_column(
        String(32), nullable=True, unique=True, default=None
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default=None
    )

    # ── Identity ─────────────────────────────────────────────────────
    role: Mapped[str] = mapped_column(
        String(16), default="student"
    )  # student | parent | teacher | admin
    grade: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default=None
    )  # 小学一年级~高中三年级 | 大一~大四
    target_exam: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )  # 中考 | 高考 | 考研 | 雅思 | 托福 | 期末
    employee_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None, index=True
    )  # 职工号 — teacher employee ID
    pending_child_student_no: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )  # Internal: child's student_no stored when parent registers but child not found
    school: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=None
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None
    )

    # ── Parent linkage ───────────────────────────────────────────────
    parent_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("learners.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # ── Relationships ────────────────────────────────────────────────
    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel", back_populates="learner", cascade="all, delete-orphan"
    )
    # Children linked to this parent
    children: Mapped[list["LearnerModel"]] = relationship(
        "LearnerModel",
        back_populates="parent",
        remote_side="LearnerModel.parent_id",
        foreign_keys="LearnerModel.parent_id",
    )
    parent: Mapped[Optional["LearnerModel"]] = relationship(
        "LearnerModel",
        back_populates="children",
        remote_side="LearnerModel.id",
        foreign_keys="LearnerModel.parent_id",
    )


# ── Session ──────────────────────────────────────────────────────────────

class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    learner_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("learners.id"), nullable=True, index=True, default=None
    )
    subject_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, default=None
    )
    title: Mapped[str] = mapped_column(String(256), default="未命名会话")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    learner: Mapped[Optional["LearnerModel"]] = relationship(
        "LearnerModel", back_populates="sessions"
    )
    messages: Mapped[list["MessageModel"]] = relationship(
        "MessageModel", back_populates="session", cascade="all, delete-orphan"
    )
    profile_snapshots: Mapped[list["ProfileSnapshotModel"]] = relationship(
        "ProfileSnapshotModel", back_populates="session", cascade="all, delete-orphan"
    )
    learning_paths: Mapped[list["LearningPathModel"]] = relationship(
        "LearningPathModel", back_populates="session", cascade="all, delete-orphan"
    )
    resources: Mapped[list["ResourceModel"]] = relationship(
        "ResourceModel", back_populates="session", cascade="all, delete-orphan"
    )
    events: Mapped[list["LearningEventModel"]] = relationship(
        "LearningEventModel", back_populates="session", cascade="all, delete-orphan"
    )
    daily_tasks: Mapped[list["DailyTaskModel"]] = relationship(
        "DailyTaskModel", back_populates="session", cascade="all, delete-orphan"
    )


# ── Message ──────────────────────────────────────────────────────────────

class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="messages")


# ── Profile Snapshot ─────────────────────────────────────────────────────

class ProfileSnapshotModel(Base):
    __tablename__ = "profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    weaknesses: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    readiness_score: Mapped[float | None] = mapped_column(nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="profile_snapshots")


# ── Learning Path ────────────────────────────────────────────────────────

class LearningPathModel(Base):
    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(String(64), default="")
    course_name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    stages: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    overall_progress: Mapped[int] = mapped_column(Integer, default=0)
    estimated_days: Mapped[int] = mapped_column(Integer, default=14)
    textbook_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )  # linked textbook ID (no FK — textbooks may be deleted independently)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="learning_paths")


# ── Resource (Resource Library Snapshot) ──────────────────────────────────

class ResourceModel(Base):
    """Per-session resource library entry — stores the full personalised resource
    data generated by the ResourceAgent, including structured content for
    mindmaps, quizzes, code blocks, and PPT outlines."""

    __tablename__ = "resources"

    # ── Identity ──────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )

    # ── Core metadata ─────────────────────────────────────────────────
    type: Mapped[str] = mapped_column(String(32), default="lecture")  # lecture|mindmap|quiz|reading|practice|multimodal|case_study|video|ppt
    title: Mapped[str] = mapped_column(String(256), default="学习资源")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # ── Classification ────────────────────────────────────────────────
    knowledge_points: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    difficulty: Mapped[str] = mapped_column(String(16), default="easy")  # easy|medium|hard
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20)
    format: Mapped[str] = mapped_column(String(16), default="text")   # text|diagram|video|code|quiz

    # ── Structured content (type-specific) ────────────────────────────
    mermaid_def: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    code_blocks: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    questions: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    ppt_outline: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    resource_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, default=None)

    # ── State & provenance ────────────────────────────────────────────
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    study_status: Mapped[str] = mapped_column(String(16), default="new")  # new|in_progress|completed
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String(16), default="agent_generated")   # db|agent_generated|system_inferred
    related_stage_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    related_chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    related_section_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="resources")


# ── Learning Event ───────────────────────────────────────────────────────

class LearningEventModel(Base):
    __tablename__ = "learning_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), default="generic")
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="events")


# ── Daily Task ───────────────────────────────────────────────────────────

class DailyTaskModel(Base):
    """A single day's task within a learning path stage.

    Enables per-day task completion tracking and cross-subject
    today's-todolist aggregation.  Source-tracking distinguishes
    agent-generated tasks from rule-based fallback derivations.
    """

    __tablename__ = "daily_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    day_index: Mapped[int] = mapped_column(Integer, default=1)
    day_label: Mapped[str] = mapped_column(String(32), default="第1天")
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String(32), default="agent_generated")
    # agent_generated | rule_fallback
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="daily_tasks")


# ── Question Bank ─────────────────────────────────────────────────────────

class QuestionModel(Base):
    """A question in the admin-managed question bank.

    Content is stored as JSON: {stem, options[], answer, explanation, hints[]}.
    Supports choice, fill, truefalse, and shortanswer types.

    Review workflow: draft → (submit) → pending_review → approve → published
                                                 └→ reject → draft
    """

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(64), index=True, default="")
    knowledge_point: Mapped[str] = mapped_column(String(128), index=True, default="")
    type: Mapped[str] = mapped_column(String(16), default="choice")  # choice|fill|truefalse|shortanswer
    difficulty: Mapped[str] = mapped_column(String(8), default="medium")  # easy|medium|hard|challenge
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|published|archived
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(default=0.0)

    # ── Review workflow ─────────────────────────────────────────────────
    review_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default=None
    )  # None (not submitted) | pending_review | approved | rejected
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="SET NULL"), nullable=True, default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    # ── Difficulty calibration ──────────────────────────────────────────
    calibrated_difficulty: Mapped[float | None] = mapped_column(
        nullable=True, default=None
    )  # 0.0-1.0 computed from actual student performance

    created_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="SET NULL"), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Knowledge Point Graph ────────────────────────────────────────────────

class KnowledgePointModel(Base):
    """A node in the subject knowledge graph (DAG).

    prerequisites is a JSON list of knowledge_point IDs that must be
    mastered before this node. This DAG drives M5's shortest-path planner.
    """

    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(64), index=True, default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    prerequisites: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)  # list[str] of KP ids
    difficulty: Mapped[str] = mapped_column(String(8), default="medium")
    importance: Mapped[int] = mapped_column(Integer, default=5)  # 1-10
    chapter: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    grade_level: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Student Questions ──────────────────────────────────────────────────────

class StudentQuestionModel(Base):
    """A question served to students, generated per-session by the LLM or
    pulled from the admin question bank.

    Follows the Question schema defined in docs/api-questions.md.
    source_question_id optionally links back to QuestionModel (admin bank).
    """

    __tablename__ = "student_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    question_set_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    session_id: Mapped[str] = mapped_column(
        String(64), index=True
    )  # May be a real session ID or synthetic like "class_{classId}" for teacher-pushed
    source_question_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )  # FK to QuestionModel.id (admin bank), optional
    type: Mapped[str] = mapped_column(String(16), default="choice")  # choice|fill|truefalse|shortanswer
    stem: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    correct: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    difficulty: Mapped[str] = mapped_column(String(8), default="medium")  # easy|medium|hard
    knowledge_points: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    scoring_rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String(32), default="llm_generated")  # llm_generated|rule_based_fallback
    quality_status: Mapped[str] = mapped_column(String(16), default="passed")  # passed|warning|fallback
    # ── M3: 人工审核相关字段 ──
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    review_status: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    revision_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── System Config ─────────────────────────────────────────────────────────

class SystemConfigModel(Base):
    """Key-value system configuration, editable by admins via the dashboard.

    Supports hot-reload for feature flags; LLM/agent settings need restart.
    """

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    category: Mapped[str] = mapped_column(String(32), default="general")  # general|llm|agent|feature
    updated_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="SET NULL"), nullable=True, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Question & Grading (M3 + M4) ────────────────────────────────────────────


class PracticeQuestionModel(Base):
    __tablename__ = "practice_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    question_set_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(16), default="choice")
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    correct: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    difficulty: Mapped[str] = mapped_column(String(8), default="medium")
    knowledge_points: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    scoring_rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String(32), default="llm_generated")
    quality_status: Mapped[str] = mapped_column(String(16), default="passed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AnswerRecordModel(Base):
    __tablename__ = "answer_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    question_id: Mapped[str] = mapped_column(String(32), index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None, index=True)
    student_answer: Mapped[str] = mapped_column(Text)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    dimension_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    dimension_feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    error_type: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    error_label: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    error_explanation: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    error_action: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    suggestions: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    strengths: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String(32), default="llm_generated")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Quiz (M5) ──────────────────────────────────────────────────────────


class QuizModel(Base):
    """A lightweight instant quiz — generated on the fly for a section or
    knowledge point. Not archived in the resource library.

    Questions are stored in PracticeQuestionModel with question_set_id
    matching this quiz's id.  scope_type drives which scope-id field is
    authoritative.
    """

    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    # ── Scope linking ─────────────────────────────────────────────
    scope_type: Mapped[str] = mapped_column(
        String(32), default="knowledge_point"
    )  # knowledge_point | section | chapter | stage | path
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    path_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    stage_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    section_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    knowledge_point_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # ── Content snapshot ─────────────────────────────────────────
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    questions: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # [{question_id, type, stem_abbr}, …]

    # ── Provenance ───────────────────────────────────────────────
    source: Mapped[str] = mapped_column(String(32), default="llm_generated")
    archive_policy: Mapped[str] = mapped_column(String(16), default="none")  # "none"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ExamSetModel(Base):
    """A heavyweight exam / practice set — persistent, archivable, and
    supports multiple attempts.  Visible in the practice centre.

    The same scope-link fields as QuizModel, plus metadata for the
    practice-centre listing (difficulty distribution, estimated time,
    total score) and status tracking.
    """

    __tablename__ = "exam_sets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    # ── Scope linking ─────────────────────────────────────────────
    scope_type: Mapped[str] = mapped_column(
        String(32), default="chapter"
    )  # chapter | stage | path
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    path_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    stage_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    knowledge_point_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # ── Content ──────────────────────────────────────────────────
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    difficulty_distribution: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # {"easy": 3, "medium": 5, "hard": 2}
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    questions: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # [{question_id, type, difficulty, score}, …]

    # ── Metadata ─────────────────────────────────────────────────
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    total_score: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(
        String(16), default="not_started"
    )  # not_started | in_progress | completed

    # ── Provenance ───────────────────────────────────────────────
    source: Mapped[str] = mapped_column(String(32), default="llm_generated")
    archive_policy: Mapped[str] = mapped_column(String(16), default="archive")  # archive
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AttemptModel(Base):
    """A single attempt at a quiz or an exam set — groups multiple
    AnswerRecordModel rows into one session.

    An attempt belongs to exactly one quiz OR one exam set (not both).
    Individual answers link back via AnswerRecordModel.attempt_id.
    """

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    # ── Polymorphic parent ────────────────────────────────────
    quiz_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, index=True
    )
    exam_set_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, index=True
    )

    # ── Answers snapshot ──────────────────────────────────────
    answers: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # [{question_id, student_answer, score}, …]
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    max_score: Mapped[int] = mapped_column(Integer, default=100)

    # ── Status ────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(16), default="in_progress"
    )  # in_progress | submitted | graded
    learner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    # ── Timestamps ────────────────────────────────────────────
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Class Subject (Teacher-managed classroom) ────────────────────────────


class ClassSubjectModel(Base):
    """A subject managed by a teacher with an invite-code for student enrollment.

    Class subjects differ from personal subjects (localStorage-based):
    - Created by teachers, joined by students via invite code
    - Teacher can view/manage roster and push exercises to all enrolled students
    - Teacher CANNOT see students' privately generated content
    - Students CANNOT modify teacher-pushed content but can create their own
    """

    __tablename__ = "class_subjects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    subject: Mapped[str] = mapped_column(String(64), default="")
    teacher_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    teacher: Mapped["LearnerModel"] = relationship("LearnerModel")


class ClassSubjectMemberModel(Base):
    """Many-to-many join: students enrolled in a class subject."""

    __tablename__ = "class_subject_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("class_subjects.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("class_id", "student_id", name="uq_class_member"),
    )


class ClassPushModel(Base):
    """A teacher-pushed exercise set to a class.

    When a teacher pushes questions, StudentQuestionModel records are created
    with source="teacher_pushed" and session_id="class_{classId}" so the
    existing grading pipeline works without changes.
    """

    __tablename__ = "class_pushes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    class_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("class_subjects.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Personal Subject (Student-managed) ─────────────────────────────────────


class PersonalSubjectModel(Base):
    """A personal subject created by a student for self-directed learning.

    Stored server-side so subjects are visible across browsers and to
    bound parent accounts.  Differs from ClassSubjectModel:
    - Created by individual students, not teachers
    - No invite code, membership roster, or exercise push mechanism
    - Visible to the creating student and their bound parent(s)
    """

    __tablename__ = "personal_subjects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    learner_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    textbook_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("textbooks.id", ondelete="SET NULL"), nullable=True, default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    learner: Mapped["LearnerModel"] = relationship("LearnerModel")
    textbook: Mapped[Optional["TextbookModel"]] = relationship("TextbookModel", foreign_keys=[textbook_id])

    __table_args__ = (
        UniqueConstraint("learner_id", "name", name="uq_personal_subject_learner_name"),
    )


# ── Textbook ──────────────────────────────────────────────────────────────


class TextbookModel(Base):
    """A PDF textbook uploaded for a personal subject.

    Stores metadata about the uploaded file, processing status, and the
    LLM-recognized chapter/section structure as JSON.

    One textbook per subject (unique constraint on subject_id).
    """

    __tablename__ = "textbooks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    learner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    filename: Mapped[str] = mapped_column(String(256), default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(64), default="application/pdf")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(16), default="uploading"
    )  # uploading | processing | ready | error
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # Full chapter/section structure from LLM parsing:
    # [{chapter_id, title, order, start_page, end_page,
    #   sections: [{section_id, title, order, start_page, end_page,
    #               estimated_minutes, knowledge_points}]}]
    chapters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    subject: Mapped["PersonalSubjectModel"] = relationship(
        "PersonalSubjectModel", foreign_keys=[subject_id]
    )


class TextbookPageContentModel(Base):
    """Per-page extracted markdown text from a textbook PDF.

    Used by quiz generation, smart tutor, and other AI features
    as the equivalent of generated lecture notes.
    """

    __tablename__ = "textbook_page_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    textbook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("textbooks.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, default=1)  # 1-indexed
    content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    page_label: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )  # e.g. "xiv", "12"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── User Preferences ────────────────────────────────────────────────────────


class UserPreferencesModel(Base):
    """Per-learner UI and learning preferences, synced across browsers.

    Separated from ProfileSnapshotModel (AI-derived dimensions) because
    these are user-controlled settings: theme, font size, difficulty
    preference, learning style, and other knobs the user sets explicitly.
    """

    __tablename__ = "user_preferences"

    learner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    # JSON blob storing:
    #   defaultDuration, difficulty, learningStyle, aiStyle,
    #   autoDiagnose, diagnoseDepth, learningTracking,
    #   ebbinghausReminder, theme, fontSize
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Assessment State (closed-loop tracking, survives restarts) ──────────

class AssessmentStateModel(Base):
    """Persistent per-session assessment tracking state for the closed-loop.

    Replaces the in-memory ``AssessmentStateTracker._states`` dict so that
    event counters, mastery snapshots, and diagnosis timestamps survive
    server restarts.
    """

    __tablename__ = "assessment_states"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, index=True
    )
    # Timestamp of the last diagnosis run (epoch seconds)
    last_diagnosis_at: Mapped[float] = mapped_column(default=0.0)
    # mastery snapshot:  {kp_name: score, ...}
    last_mastery_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    # Counters since last diagnosis
    events_since_last_diagnosis: Mapped[int] = mapped_column(Integer, default=0)
    resource_completions_since_diagnosis: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Planning Draft ────────────────────────────────────────────────────────

class PlanningDraftModel(Base):
    """Guided learning path planning draft — scoped to learner + session + subject."""
    __tablename__ = "planning_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    learner_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[str] = mapped_column(String(64), index=True, default="")

    # Planning fields
    topic: Mapped[str] = mapped_column(String(256), default="")
    goal: Mapped[str] = mapped_column(String(64), default="")
    current_level: Mapped[str] = mapped_column(String(64), default="")
    daily_time: Mapped[str] = mapped_column(String(64), default="")
    target_duration: Mapped[str] = mapped_column(String(64), default="")
    resource_preferences: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(32), default="collecting")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    session: Mapped["SessionModel"] = relationship("SessionModel")
