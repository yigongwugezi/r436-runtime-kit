"""Agent service — clean separation between trigger and read paths.

Responsibilities:
- ``run_agents()`` — trigger the full multi-agent pipeline, persist results, return them.
- ``get_profile()`` — read latest profile from DB (no side effects).
- ``get_learning_path()`` — read latest learning path from DB.
- ``get_resources()`` — read resources from DB.
- ``get_analytics()`` — read learning analytics from DB.

This ensures that GET endpoints never accidentally trigger agent runs.
"""

from __future__ import annotations

from typing import Any

from app.db.engine import SessionLocal
from app.db.repository import (
    get_event_analytics,
    get_latest_learning_path as repo_get_latest_path,
    get_latest_profile as repo_get_latest_profile,
    get_resources as repo_get_resources,
)
from app.services.conversation_state import conversation_store
from app.services.course_catalog import course_catalog
from app.services.orchestrator import AgentOrchestrator


# ── Trigger: run the full agent pipeline ──────────────────────────────


def run_agents(
    session_id: str,
    user_message: str,
    course_id: str | None = None,
) -> dict[str, Any]:
    """Run the multi-agent pipeline, persist results, and return them.

    Steps:
    1. Build an enriched prompt from ConversationStore facts + latest message.
    2. Match the target course (or use the caller-supplied ``course_id``).
    3. Call ``AgentOrchestrator.run()``.
    4. Save results via ``ConversationStore.set_result()`` (DB + in-memory).
    5. Return the orchestrator result dict.

    Args:
        session_id: Current session identifier.
        user_message: The latest user message.
        course_id: Optional explicit course ID.  If *None*, matched from facts.

    Returns:
        The orchestrator result dict (see ``OrchestratorResult`` schema).

    Raises:
        RuntimeError: If the orchestrator returns no result at all.
    """
    state = conversation_store.get(session_id)

    # Build enriched prompt from conversation state
    agent_message = conversation_store.profile_prompt(state, latest_message=user_message)

    # Match course
    selected_course = course_catalog.match_course(
        state.facts.get("target_course") or user_message,
        default="ai_intro",
    )
    resolved_course_id = course_id or str(
        (selected_course or {}).get("course_id") or "ai_intro"
    )

    # Run orchestrator
    orchestrator = AgentOrchestrator()
    result = orchestrator.run(
        session_id=session_id,
        course_id=resolved_course_id,
        user_message=agent_message,
    )

    # Attach course metadata
    if selected_course:
        result["course"] = {
            "course_id": selected_course.get("course_id"),
            "course_name": selected_course.get("course_name"),
            "description": selected_course.get("description", ""),
            "chapter_count": selected_course.get(
                "chapter_count", len(selected_course.get("chapters", []))
            ),
        }

    # Persist to DB + in-memory cache
    conversation_store.set_result(session_id, result)

    return result


# ── Read: get latest profile from DB ──────────────────────────────────


def get_profile(session_id: str) -> dict[str, Any] | None:
    """Read the latest profile snapshot from the database.

    Returns *None* if no profile has been saved for this session yet.
    """
    try:
        db = SessionLocal()
        snapshot = repo_get_latest_profile(db, session_id)
        if snapshot is None:
            return None

        dimensions = snapshot.dimensions or []
        if isinstance(dimensions, dict):
            dimensions = [
                {"key": key, **value} if isinstance(value, dict) else {"key": key, "value": str(value)}
                for key, value in dimensions.items()
            ]

        weaknesses = snapshot.weaknesses or []
        preferences = snapshot.preferences or {}
        readiness_score = snapshot.readiness_score or 0.0

        return {
            "id": session_id,
            "dimensions": dimensions,
            "weaknesses": weaknesses,
            "preferences": preferences,
            "readiness_score": readiness_score,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        }
    finally:
        db.close()


# ── Read: get latest learning path from DB ────────────────────────────


def get_learning_path(session_id: str) -> dict[str, Any] | None:
    """Read the latest learning path from the database.

    Returns *None* if no path has been saved yet.
    """
    try:
        db = SessionLocal()
        path = repo_get_latest_path(db, session_id)
        if path is None:
            return None

        return {
            "id": path.id,
            "course_id": path.course_id,
            "course_name": path.course_name,
            "stages": path.stages or [],
            "overall_progress": path.overall_progress or 0,
            "estimated_days": path.estimated_days or 14,
            "created_at": path.created_at.isoformat() if path.created_at else None,
            "updated_at": path.updated_at.isoformat() if path.updated_at else None,
        }
    finally:
        db.close()


# ── Read: get resources from DB ───────────────────────────────────────


def get_resources(session_id: str) -> list[dict[str, Any]]:
    """Read all resources for a session from the database."""
    try:
        db = SessionLocal()
        rows = repo_get_resources(db, session_id)
        return [
            {
                "id": r.id,
                "type": r.type or "lecture",
                "title": r.title or "学习资源",
                "description": r.description or "",
                "content": r.content or "",
                "tags": r.tags or [],
                "bookmarked": r.bookmarked or False,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


# ── Read: get learning analytics from DB ──────────────────────────────


def get_analytics(session_id: str) -> dict[str, Any]:
    """Read learning analytics summary from the database."""
    try:
        db = SessionLocal()
        return get_event_analytics(db, session_id)
    finally:
        db.close()
