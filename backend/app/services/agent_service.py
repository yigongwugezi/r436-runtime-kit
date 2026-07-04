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
# AgentOrchestrator removed — OpenClaw handles all orchestration
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
    agents_filter: list[str] | None = None,
) -> dict[str, Any]:
    """OpenClaw 统一编排——直接转发到 OpenClaw 引擎。"""
    from app.services.openclaw_bridge import process_message
    result = process_message(user_message, session_id)
    results = result.get("results", {})
    events = result.get("events", [])

    output = {
        "session_id": session_id,
        "course_id": course_id or "",
        "agent_steps": events,
        "agents_run": [e.get("agent", "") for e in events if e.get("status") == "done"],
        "pipeline_executed": True,
    }
    # 画像/路径/资源从 OpenClaw 结果提取
    for key in ("profile", "plan_reply", "resources", "grading", "questions"):
        if key in results:
            output[key] = results[key]

    # 持久化
    _persist_raw(session_id, results)

    return output


def _persist_raw(session_id: str, results: dict) -> None:
    import json as _json
    try:
        conversation_store.set_result(session_id, {"openclaw_raw": _json.dumps(results, ensure_ascii=False)})
    except Exception:
        pass


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