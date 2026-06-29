"""SQLAlchemy ORM models for EduAgent persistence.

Design notes:
- session_id is the primary access key; learner_id links sessions to a learner.
- learner_id is nullable for backward compatibility with pre-Learner sessions.
- JSON columns use SQLAlchemy's JSON type (TEXT in SQLite, JSONB in PostgreSQL).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
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
    """

    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(128), default="学习者")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel", back_populates="learner", cascade="all, delete-orphan"
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
