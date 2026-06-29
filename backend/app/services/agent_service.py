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

from typing import Any, Callable

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
from app.utils.profile_normalizer import PROFILE_DIMENSION_LABELS, normalize_profile_dimensions


# ── Trigger: run the full agent pipeline ──────────────────────────────


def _profile_item(
    key: str,
    value: str,
    source: str = "user_input",
    confidence: float = 1.0,
    explanation: str | None = None,
    evidence: str | None = None,
    score: int = 70,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": PROFILE_DIMENSION_LABELS.get(key, key),
        "value": value,
        "score": score,
        "confidence": confidence,
        "source": source,
        "explanation": explanation or value,
        "evidence": evidence or value,
    }


def _apply_state_facts_to_result(result: dict[str, Any], facts: dict[str, str], course: dict[str, Any] | None = None) -> None:
    profile = result.setdefault("profile", {})
    course_name = str((course or {}).get("course_name") or facts.get("target_course") or "").strip()
    overrides = {
        "major_background": facts.get("background", ""),
        "knowledge_base": facts.get("knowledge_base", ""),
        "learning_goal": facts.get("learning_goal", ""),
        "cognitive_style": facts.get("preference", ""),
        "error_patterns": facts.get("weak_points", ""),
        "interest_direction": facts.get("target_course", ""),
        "learning_rhythm": facts.get("time_budget", ""),
    }
    for key, value in overrides.items():
        if value:
            profile[key] = _profile_item(
                key,
                str(value),
                source="user_input",
                confidence=1.0,
                explanation=f"该维度直接来自用户描述：{value}",
                evidence=str(value),
            )

    if course_name:
        profile["interest_direction"] = _profile_item(
            "interest_direction",
            course_name,
            source="user_input",
            confidence=0.9,
            explanation=f"目标课程已识别为：{course_name}",
            evidence=course_name,
            score=82,
        )
        profile.setdefault(
            "learning_progress",
            _profile_item(
                "learning_progress",
                f"正在推进{course_name}学习",
                source="inferred",
                confidence=0.8,
                explanation="根据目标课程和当前对话推断学习进度仍处于推进阶段。",
                evidence=course_name,
                score=60,
            ),
        )


def run_agents(
    session_id: str,
    user_message: str,
    course_id: str | None = None,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    """Run the multi-agent pipeline, persist results, and return them.

    Steps:
    1. Build context from ConversationStore facts + conversation history.
    2. Match the target course (or use the caller-supplied ``course_id``).
    3. Call ``AgentOrchestrator.run()``.
    4. Save results via ``ConversationStore.set_result()`` (DB + in-memory).
    5. Return the orchestrator result dict.

    Args:
        session_id: Current session identifier.
        user_message: The latest user message (raw, not wrapped).
        course_id: Optional explicit course ID.  If *None*, matched from facts.
        progress_callback: Optional callback forwarded to Orchestrator.

    Returns:
        The orchestrator result dict (see ``OrchestratorResult`` schema).

    Raises:
        RuntimeError: If the orchestrator returns no result at all.
    """
    state = conversation_store.get(session_id)

    # Build enriched prompt from conversation state
    agent_message = conversation_store.profile_prompt(state, latest_message=user_message)

    # Build conversation context (full dialogue history for LLM agents)
    conversation_context = "\n".join(
        f"{'学生' if m['role'] == 'user' else '助手'}: {m['content']}"
        for m in state.messages[-20:]
    )

    # Match course — only if caller hasn't already supplied one
    selected_course = None
    if course_id and course_id.startswith("custom_"):
        resolved_course_id = course_id
    elif course_id:
        selected_course = course_catalog.get_course(course_id)
        resolved_course_id = course_id
    else:
        selected_course = course_catalog.match_course(
            state.facts.get("target_course") or user_message,
        )
        resolved_course_id = course_id or str(
            (selected_course or {}).get("course_id") or f"custom_{abs(hash(str(state.facts.get('target_course') or user_message))) % 10000:04d}"
        )

    # Run orchestrator
    orchestrator = AgentOrchestrator()
    facts = dict(state.facts)
    facts["_raw_user_message"] = user_message
    facts["_conversation_context"] = conversation_context
    result = orchestrator.run(
        session_id=session_id,
        course_id=resolved_course_id,
        user_message=user_message,
        profile_facts=facts,
        progress_callback=progress_callback,
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

    _apply_state_facts_to_result(result, state.facts, selected_course)

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

        dimensions = normalize_profile_dimensions(snapshot.dimensions)

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


def _extract_stage_id(r) -> str:
    """Extract related_stage_id from a ResourceModel.

    Priority:
    1. The dedicated ``related_stage_id`` column (new resources).
    2. ``knowledge_points`` list (old resources store stage_id in any position).
    3. ``tags`` list (fallback for very old data).
    """
    col = getattr(r, "related_stage_id", None)
    if col:
        return str(col)
    kps = r.knowledge_points or []
    if kps and isinstance(kps, (list, tuple)):
        for kp in kps:
            t = str(kp).strip()
            if t.startswith("stage_") or t.startswith("s") or t.startswith("custom_"):
                return t
    tags = r.tags or []
    if tags and isinstance(tags, (list, tuple)):
        for tag in tags:
            t = str(tag).strip()
            if t.startswith("stage_") or t.startswith("s"):
                return t
    return ""


def _extract_task_id(r) -> str:
    """Extract task_id from a ResourceModel."""
    col = getattr(r, "task_id", None)
    if col:
        return str(col)
    return ""


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
            "description": path.description or "",
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
    """Read all resources for a session from the database with full metadata."""
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
                "knowledge_points": r.knowledge_points or [],
                "tags": r.tags or [],
                "difficulty": r.difficulty or "easy",
                "estimated_minutes": r.estimated_minutes or 20,
                "format": r.format or "text",
                "mermaid_def": r.mermaid_def,
                "code_blocks": r.code_blocks,
                "questions": r.questions,
                "ppt_outline": r.ppt_outline,
                "bookmarked": r.bookmarked or False,
                "study_status": r.study_status or "new",
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "source": r.source or "system_inferred",
                "related_stage_id": _extract_stage_id(r),
                "task_id": r.task_id or _extract_task_id(r),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
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