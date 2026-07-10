"""Shared profile-fact helpers used across agent_service and product router.

Extracted from duplicated definitions in:
- ``app.services.agent_service``
- ``app.routers.product``

Consolidated here per IntentRouter docstring consolidation target (Phase 2).
"""

from __future__ import annotations

from typing import Any

from app.utils.profile_normalizer import PROFILE_DIMENSION_LABELS


def profile_item(
    key: str,
    value: str,
    source: str = "user_input",
    confidence: float = 1.0,
    explanation: str | None = None,
    evidence: str | None = None,
    score: int = 70,
) -> dict[str, Any]:
    """Build a single profile-dimension dict with standard fields."""
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


def apply_state_facts_to_result(
    result: dict[str, Any],
    facts: dict[str, str],
    course: dict[str, Any] | None = None,
) -> None:
    """Override profile dimensions from conversation-state facts into *result*.

    Mutates ``result`` in place, setting ``result["profile"]`` with dimension
    dicts derived from the user-supplied facts.
    """
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
            profile[key] = profile_item(
                key,
                str(value),
                source="user_input",
                confidence=1.0,
                explanation=f"该维度直接来自用户描述：{value}",
                evidence=str(value),
            )

    if course_name:
        profile["interest_direction"] = profile_item(
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
            profile_item(
                "learning_progress",
                f"正在推进{course_name}学习",
                source="inferred",
                confidence=0.8,
                explanation="根据目标课程和当前对话推断学习进度仍处于推进阶段。",
                evidence=course_name,
                score=60,
            ),
        )
