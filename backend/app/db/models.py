"""SQLAlchemy ORM models for EduAgent persistence.

Design notes:
- session_id is the primary access key in the current no-auth phase.
- user_id is nullable and reserved for future multi-user support.
- JSON columns use SQLAlchemy's JSON type (TEXT in SQLite, JSONB in PostgreSQL).
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Session ──────────────────────────────────────────────────────────────

class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, default=None
    )
    title: Mapped[str] = mapped_column(String(256), default="未命名会话")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    stages: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    overall_progress: Mapped[int] = mapped_column(Integer, default=0)
    estimated_days: Mapped[int] = mapped_column(Integer, default=14)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="learning_paths")


# ── Resource ─────────────────────────────────────────────────────────────

class ResourceModel(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32), default="lecture")
    title: Mapped[str] = mapped_column(String(256), default="学习资源")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

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
