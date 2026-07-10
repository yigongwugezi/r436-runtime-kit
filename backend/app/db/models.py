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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    learner: Mapped["LearnerModel"] = relationship("LearnerModel")


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
