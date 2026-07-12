"""Versioned, evidence-aware learner profile built from existing JSON snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from app.utils.profile_normalizer import detect_course_category


_CATEGORY_NAMES = {"cs": "computing", "math": "mathematics", "language": "language"}
_DIMENSIONS = {
    "computing": [("prerequisites", "先修知识"), ("concept_understanding", "概念理解"), ("complexity_analysis", "复杂度分析"), ("algorithmic_thinking", "算法思维"), ("code_implementation", "代码实现"), ("debugging", "调试能力")],
    "mathematics": [("conceptual_foundation", "概念基础"), ("calculus", "极限与微积分"), ("proof_reasoning", "证明推理"), ("problem_solving", "解题能力")],
    "language": [("vocabulary", "词汇"), ("grammar", "语法"), ("reading", "阅读"), ("writing", "写作")],
    "general": [("prerequisites", "先修知识"), ("concept_understanding", "概念理解"), ("practice_strategy", "练习策略"), ("self_correction", "自我纠错")],
}
_STATE_LABELS = [("interest", "当前兴趣"), ("confidence", "学习信心"), ("engagement", "投入意愿"), ("self_regulation", "自我调节"), ("pressure", "当前压力")]
_CONTEXT_KEYS = {"learning_goal", "deadline", "daily_minutes", "prior_experience", "background", "content_preferences", "resource_preferences"}
_SELF_REPORT_KEYS = {key for key, _ in _STATE_LABELS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence(source: str, detail: str) -> list[dict[str, str]]:
    return [{"source": source, "detail": detail}] if detail else []


def _dimension_map(dimensions: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {str(item.get("key")): item for item in dimensions or [] if isinstance(item, dict) and item.get("key")}


def _minutes(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:小时|h)", text, re.I)
    if match:
        return int(match.group(1)) * 60
    match = re.search(r"(\d+)\s*分钟", text)
    return int(match.group(1)) if match else None


def _category(course_name: str, course: dict[str, Any] | None) -> str:
    context = dict(course or {})
    context.setdefault("course_name", course_name)
    return _CATEGORY_NAMES.get(detect_course_category(context), "general")


def _context(facts: dict[str, Any], dimensions: dict[str, dict[str, Any]], course: dict[str, Any] | None) -> dict[str, Any]:
    course_name = str((course or {}).get("course_name") or facts.get("target_course") or dimensions.get("interest_direction", {}).get("value") or "").strip()
    time_budget = str(facts.get("time_budget") or dimensions.get("learning_rhythm", {}).get("value") or "").strip()
    preference = str(facts.get("preference") or dimensions.get("cognitive_style", {}).get("value") or "").strip()
    return {
        "subject_id": str((course or {}).get("course_id") or ""),
        "subject_name": course_name,
        "subject_category": _category(course_name, course),
        "learning_goal": str(facts.get("learning_goal") or dimensions.get("learning_goal", {}).get("value") or "").strip(),
        "deadline": "",
        "daily_minutes": _minutes(time_budget),
        "prior_experience": [str(facts["knowledge_base"])] if facts.get("knowledge_base") else [],
        "background": str(facts.get("background") or dimensions.get("major_background", {}).get("value") or "").strip(),
        "language": "zh-CN",
        "content_preferences": [preference] if preference else [],
        "resource_preferences": [],
    }


def build_profile_v2(
    *,
    dimensions: list[dict[str, Any]] | None = None,
    facts: dict[str, Any] | None = None,
    course: dict[str, Any] | None = None,
    weaknesses: list[dict[str, Any]] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert legacy profile facts/dimensions to a V2 profile without guessing scores."""
    facts = facts or {}
    legacy = _dimension_map(dimensions)
    context = _context(facts, legacy, course)
    if existing and existing.get("profile_version") == 2:
        profile = dict(existing)
        profile["subject_context"] = {**context, **(existing.get("subject_context") or {})}
        profile["updated_at"] = _now()
        return profile

    category = context["subject_category"]
    weak_text = " ".join(str(value) for value in (facts.get("weak_points"), legacy.get("error_patterns", {}).get("value", "")) if value)
    subject_dimensions = []
    for key, label in _DIMENSIONS[category]:
        has_user_evidence = bool(weak_text or facts.get("knowledge_base"))
        status = "tentative" if has_user_evidence else "unassessed"
        subject_dimensions.append({
            "key": key,
            "label": label,
            "status": status,
            "score": None,
            "confidence": "low" if has_user_evidence else "low",
            "evidence": _evidence("conversation", weak_text or str(facts.get("knowledge_base") or "")),
            "recommended_action": "完成一次针对本项的练习或诊断后再评估。",
            "updated_at": _now(),
        })

    knowledge_mastery = []
    for item in weaknesses or []:
        label = str(item.get("topic") or item.get("name") or "").strip()
        if label:
            knowledge_mastery.append({"knowledge_id": label, "label": label, "status": "weak", "confidence": "low", "evidence": _evidence("conversation", str(item.get("reason") or label)), "updated_at": _now()})
    if weak_text and not knowledge_mastery:
        knowledge_mastery.append({"knowledge_id": "self_reported_weakness", "label": weak_text, "status": "weak", "confidence": "low", "evidence": _evidence("conversation", weak_text), "updated_at": _now()})

    states = [{"key": key, "label": label, "status": "unassessed", "self_report": None, "system_estimate": None, "level": "未评估", "confidence": "low", "evidence": [], "updated_at": _now()} for key, label in _STATE_LABELS]
    collected = sum(bool(context[key]) for key in ("subject_name", "learning_goal", "daily_minutes", "prior_experience", "background", "content_preferences"))
    return {"profile_version": 2, "subject_context": context, "general_states": states, "subject_dimensions": subject_dimensions, "knowledge_mastery": knowledge_mastery, "evidence_summary": {"conversation": collected, "diagnostic": 0, "practice": 0, "behavior": 0}, "profile_completeness": round(collected / 6, 2), "updated_at": _now()}


def update_context(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    context = profile.setdefault("subject_context", {})
    for key, value in updates.items():
        if key in _CONTEXT_KEYS:
            context[key] = value
    profile["updated_at"] = _now()
    return profile


def update_self_report(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    by_key = {item["key"]: item for item in profile.get("general_states", []) if isinstance(item, dict)}
    for key, value in updates.items():
        if key not in _SELF_REPORT_KEYS:
            continue
        score = max(0, min(100, int(value)))
        state = by_key.get(key)
        if state:
            state.update({"self_report": score, "status": "assessed", "level": "用户自评", "evidence": _evidence("self_report", f"用户自评 {score}/100"), "updated_at": _now()})
    profile["updated_at"] = _now()
    return profile


def assess_interest(profile: dict[str, Any], answers: list[int]) -> dict[str, Any]:
    values = [max(1, min(5, int(answer))) for answer in answers[:5]]
    if not values:
        return profile
    estimate = round(sum(values) / len(values) * 20)
    for state in profile.get("general_states", []):
        if state.get("key") == "interest":
            state.update({"status": "assessed", "system_estimate": estimate, "level": "较高" if estimate >= 70 else "中等" if estimate >= 40 else "较低", "confidence": "medium", "evidence": _evidence("interest_calibration", "完成当前学科兴趣校准问答"), "updated_at": _now()})
    profile["updated_at"] = _now()
    return profile


INTEREST_QUESTIONS = ["我觉得这门课程的内容值得投入时间。", "即使没有考试，我也愿意继续了解其中的内容。", "我愿意为这门课程主动完成额外练习。"]
