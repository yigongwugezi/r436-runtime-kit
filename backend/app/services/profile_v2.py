"""Stable, evidence-aware learner profile V2 built from existing JSON data."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from app.utils.profile_normalizer import detect_course_category


_CATEGORY_NAMES = {"cs": "computing", "math": "mathematics", "language": "language"}
_DIMENSIONS = {
    "computing": [("prerequisites", "\u5148\u4fee\u77e5\u8bc6"), ("concept_understanding", "\u6982\u5ff5\u7406\u89e3"), ("complexity_analysis", "\u590d\u6742\u5ea6\u5206\u6790"), ("algorithmic_thinking", "\u7b97\u6cd5\u601d\u7ef4"), ("code_implementation", "\u4ee3\u7801\u5b9e\u73b0"), ("debugging", "\u8c03\u8bd5\u80fd\u529b")],
    "mathematics": [("conceptual_foundation", "\u6982\u5ff5\u57fa\u7840"), ("calculus", "\u5fae\u79ef\u5206\u4e0e\u6781\u9650"), ("proof_reasoning", "\u63a8\u7406\u8bba\u8bc1"), ("problem_solving", "\u89e3\u9898\u7b56\u7565"), ("modeling_transfer", "\u5efa\u6a21\u8fc1\u79fb")],
    "language": [("vocabulary", "\u8bcd\u6c47"), ("grammar", "\u8bed\u6cd5"), ("reading", "\u9605\u8bfb"), ("writing", "\u5199\u4f5c")],
    "general": [("prerequisites", "\u5148\u4fee\u77e5\u8bc6"), ("concept_understanding", "\u6982\u5ff5\u7406\u89e3"), ("practice_strategy", "\u7ec3\u4e60\u7b56\u7565"), ("self_correction", "\u81ea\u6211\u7ea0\u9519")],
}
_STATE_LABELS = [("interest", "\u5f53\u524d\u5174\u8da3"), ("confidence", "\u5b66\u4e60\u4fe1\u5fc3"), ("engagement", "\u6295\u5165\u610f\u613f"), ("self_regulation", "\u81ea\u6211\u8c03\u8282"), ("pressure", "\u5f53\u524d\u538b\u529b")]
_CONTEXT_KEYS = {"learning_goal", "deadline", "daily_minutes", "prior_experience", "background", "content_preferences", "resource_preferences"}
_SELF_REPORT_KEYS = {key for key, _ in _STATE_LABELS}
_MISSING = {"", "\u5f85\u8865\u5145", "\u672a\u8bc4\u4f30", "\u672a\u77e5", "\u6682\u65e0", "none", "null", "undefined"}
_PREFERENCES = (("example_first", "\u5148\u770b\u4f8b\u9898"), ("practice_after_explanation", "\u8bb2\u89e3\u540e\u7ec3\u4e60"), ("definition_first", "\u5148\u8bb2\u5b9a\u4e49"), ("visual_explanation", "\u56fe\u89e3"), ("step_by_step", "\u5206\u6b65\u8bb2\u89e3"), ("concise_explanation", "\u7b80\u6d01\u8bb2\u89e3"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _missing(value: Any) -> bool:
    if value is None or value == 50:
        return True
    if isinstance(value, dict):
        keys = ("value", "content", "name", "label", "score", "self_report", "system_estimate")
        return not any(key in value and not _missing(value[key]) for key in keys)
    if isinstance(value, (list, tuple, set)):
        return not any(not _missing(item) for item in value)
    text = str(value).strip().lower()
    return text in _MISSING or text == "\u8bc1\u636e\u4e0d\u8db3"


def _clean_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else re.split(r"[\u3001,\uff0c;\uff1b/]", str(value or ""))
    return list(dict.fromkeys(item.strip() for item in values if not _missing(item)))


def _prior_experience(value: Any, category: str) -> list[str]:
    """Keep explicit experience, not fragments leaked from schedule parsing."""
    items = [item for item in _clean_list(value) if not re.match(r"^(?:\u6bcf\u5929|\u6bcf\u65e5|\u6bcf\u5468).*[:\uff1a]", item)]
    if category == "computing":
        items = [item for item in items if not re.fullmatch(r"\u8bed\u8a00\u57fa\u7840[:\uff1a]?(?:\u8fd8\u53ef\u4ee5|\u4e00\u822c|\u8f83\u597d)?", item)]
    return items


def _number(value: str) -> int | None:
    numbers = {"\u4e00": 1, "\u4e8c": 2, "\u4e24": 2, "\u4e09": 3, "\u56db": 4, "\u4e94": 5, "\u516d": 6, "\u4e03": 7, "\u516b": 8, "\u4e5d": 9, "\u5341": 10}
    return int(value) if value.isdigit() else numbers.get(value)


def _minutes(value: Any) -> int | None:
    if isinstance(value, int) and 1 <= value <= 1440:
        return value
    text = str(value or "")
    if text.isdigit() and 1 <= int(text) <= 1440:
        return int(text)
    match = re.search(r"(?:\u6bcf\u5929|\u6bcf\u65e5|\u4e00\u5929)\s*(?:\u53ef\u4ee5|\u80fd|\u53ef)?\s*(?:\u5b66\u4e60|\u5b66)?\s*([0-9\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+)\s*\u5c0f\u65f6", text)
    if match:
        number = _number(match.group(1))
        return number * 60 if number else None
    match = re.search(r"(?:\u6bcf\u5929|\u6bcf\u65e5|\u4e00\u5929)\s*(?:\u53ef\u4ee5|\u80fd|\u53ef)?\s*(?:\u5b66\u4e60|\u5b66)?\s*([0-9\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+)\s*\u5206\u949f", text)
    if match:
        return _number(match.group(1))
    match = re.search(r"(?:\u6bcf\u5929|\u6bcf\u65e5|\u4e00\u5929)\s*(\d+)\s*\u5c0f\u65f6", text)
    if match:
        return int(match.group(1)) * 60
    match = re.search(r"(?:\u6bcf\u5929|\u6bcf\u65e5|\u4e00\u5929)\s*(\d+)\s*\u5206\u949f", text)
    return int(match.group(1)) if match else None


def _deadline(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"([0-9\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+)\s*(\u5929|\u5468|\u6708)", text)
    if match:
        number = _number(match.group(1))
        label = {1: "\u4e00", 2: "\u4e24"}.get(number, str(number)) if number else match.group(1)
        return f"{label}{match.group(2)}"
    return text if re.search(r"\u5468\u5185|\u4e24\u5468|\u671f\u672b|\u524d|\u5185|\u6708", text) else None


def _preferences(value: Any) -> list[str]:
    text = " ".join(_clean_list(value))
    result = [key for key, label in _PREFERENCES if any(token in text for token in (key, label))]
    if "\u5148\u770b\u4f8b\u9898" in text:
        result.append("example_first")
    if any(token in text for token in ("\u7ec3\u4e60", "\u505a\u9898")) and any(token in text for token in ("\u8bb2\u89e3", "\u4f8b\u9898")):
        result.append("practice_after_explanation")
    return list(dict.fromkeys(result))


def _evidence(source: str, detail: str, targets: list[str]) -> list[dict[str, Any]]:
    if _missing(detail):
        return []
    return [{"source": source, "detail": detail, "raw_text": detail, "target_keys": targets, "confidence": "low"}]


def _category(course_name: str, course: dict[str, Any] | None) -> str:
    context = dict(course or {})
    context.setdefault("course_name", course_name)
    return _CATEGORY_NAMES.get(detect_course_category(context), "general")


def _dimension_map(dimensions: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {str(item.get("key")): item for item in dimensions or [] if isinstance(item, dict) and item.get("key")}


def _context(facts: dict[str, Any], legacy: dict[str, dict[str, Any]], course: dict[str, Any] | None) -> dict[str, Any]:
    course_name = str((course or {}).get("course_name") or facts.get("target_course") or legacy.get("interest_direction", {}).get("value") or "").strip()
    time_text = str(facts.get("time_budget") or legacy.get("learning_rhythm", {}).get("value") or "")
    preference = facts.get("content_preferences") or facts.get("preference") or legacy.get("cognitive_style", {}).get("value")
    category = _category(course_name, course)
    return {
        "subject_id": str((course or {}).get("course_id") or ""), "subject_name": course_name,
        "subject_category": category,
        "learning_goal": "" if _missing(facts.get("learning_goal")) else str(facts.get("learning_goal")).strip(),
        "deadline": _deadline(facts.get("deadline") or time_text),
        "daily_minutes": _minutes(facts.get("daily_minutes") or time_text),
        "prior_experience": _prior_experience(facts.get("prior_experience") or facts.get("knowledge_base"), category),
        "background": "" if _missing(facts.get("background")) else str(facts.get("background")).strip(),
        "language": "zh-CN", "content_preferences": _preferences(preference),
        "resource_preferences": _clean_list(facts.get("resource_preferences")),
    }


def _completeness(context: dict[str, Any]) -> float:
    """Count period and daily time as one valid schedule fact."""
    values = (
        context.get("subject_name"), context.get("learning_goal"),
        context.get("daily_minutes") or context.get("deadline"), context.get("background"),
        context.get("prior_experience"), context.get("content_preferences"),
    )
    return round(sum(not _missing(value) for value in values) / len(values), 2)


def _claims(facts: dict[str, Any]) -> list[str]:
    raw = "\u3001".join(str(facts.get(key) or "") for key in ("weak_points", "knowledge_base", "prior_experience"))
    parts = re.split(r"[\u3001,\uff0c;\uff1b\n]", raw)
    return list(dict.fromkeys(re.sub(r"^(?:\u4f46|\u6211|\u7684)", "", part).strip() for part in parts if not _missing(part)))


def _targets(claim: str, category: str) -> list[str]:
    text = claim.lower()
    if category == "computing":
        targets: list[str] = []
        if any(word in text for word in ("\u590d\u6742\u5ea6", "\u65f6\u95f4\u590d\u6742\u5ea6")): targets.append("complexity_analysis")
        if any(word in text for word in ("c\u8bed\u8a00", "python", "\u4ee3\u7801")): targets.append("code_implementation")
        if any(word in text for word in ("debug", "\u8c03\u8bd5", "\u62a5\u9519")): targets.append("debugging")
        if any(word in text for word in ("\u6570\u7ec4", "\u94fe\u8868", "\u6811", "\u6808", "\u961f\u5217")): targets.extend(["prerequisites", "concept_understanding"])
        if "\u7b97\u6cd5" in text: targets.append("algorithmic_thinking")
        return list(dict.fromkeys(targets))
    if category == "mathematics":
        return (["calculus"] if any(word in text for word in ("\u6781\u9650", "\u5fae\u79ef\u5206")) else []) + (["proof_reasoning"] if "\u8bc1\u660e" in text else [])
    if category == "language":
        return [key for key, word in (("reading", "\u9605\u8bfb"), ("writing", "\u5199\u4f5c"), ("grammar", "\u8bed\u6cd5"), ("vocabulary", "\u8bcd\u6c47")) if word in text]
    return []


def _knowledge(claims: list[str], category: str) -> list[dict[str, Any]]:
    names: list[str] = []
    for claim in claims:
        for name in ("\u6570\u7ec4", "\u94fe\u8868", "\u6811", "\u590d\u6742\u5ea6", "\u6781\u9650", "\u8bc1\u660e\u9898", "\u9605\u8bfb", "\u5199\u4f5c"):
            if name in claim and name not in names:
                names.append(name)
    return [{"knowledge_id": name, "label": name, "status": "weak", "confidence": "low", "evidence": _evidence("conversation", claim, _targets(claim, category)), "updated_at": _now()} for name in names for claim in claims if name in claim]


def build_profile_v2(*, dimensions: list[dict[str, Any]] | None = None, facts: dict[str, Any] | None = None, course: dict[str, Any] | None = None, weaknesses: list[dict[str, Any]] | None = None, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    facts, legacy = facts or {}, _dimension_map(dimensions)
    context = _context(facts, legacy, course)
    if existing and existing.get("profile_version") == 2:
        profile = dict(existing)
        previous = existing.get("subject_context") if isinstance(existing.get("subject_context"), dict) else {}
        profile["subject_context"] = {key: (value if not _missing(value) else previous.get(key)) for key, value in {**previous, **context}.items()}
        profile["profile_completeness"] = _completeness(profile["subject_context"])
        return profile
    category, claims = context["subject_category"], _claims(facts)
    subject_dimensions = []
    for key, label in _DIMENSIONS[category]:
        matched = [claim for claim in claims if key in _targets(claim, category)]
        subject_dimensions.append({"key": key, "label": label, "status": "tentative" if matched else "unassessed", "score": None, "confidence": "low", "evidence": [item for claim in matched for item in _evidence("conversation", claim, [key])], "recommended_action": "\u5b8c\u6210\u9488\u5bf9\u672c\u9879\u7684\u7ec3\u4e60\u6216\u8bca\u65ad\u540e\u518d\u8bc4\u4f30\u3002", "updated_at": _now()})
    mastery = _knowledge(claims, category)
    if not mastery:
        for item in weaknesses or []:
            name = str(item.get("topic") or item.get("name") or "").strip()
            if name and not _missing(name): mastery.append({"knowledge_id": name, "label": name, "status": "weak", "confidence": "low", "evidence": _evidence("diagnostic", str(item.get("reason") or name), []), "updated_at": _now()})
    states = [{"key": key, "label": label, "status": "unassessed", "self_report": None, "system_estimate": None, "level": "\u672a\u8bc4\u4f30", "confidence": "low", "evidence": [], "updated_at": _now()} for key, label in _STATE_LABELS]
    return {"profile_version": 2, "subject_context": context, "general_states": states, "subject_dimensions": subject_dimensions, "knowledge_mastery": mastery, "evidence_summary": {"conversation": len(claims), "diagnostic": len(weaknesses or []), "practice": 0, "behavior": 0}, "profile_completeness": _completeness(context), "updated_at": _now()}


def update_context(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    context = profile.setdefault("subject_context", {})
    for key, value in updates.items():
        if key not in _CONTEXT_KEYS: continue
        if key == "daily_minutes": value = _minutes(value) if not isinstance(value, int) else _minutes(value)
        elif key in {"prior_experience", "resource_preferences"}: value = _clean_list(value)
        elif key == "content_preferences": value = _preferences(value)
        elif key == "deadline": value = _deadline(value)
        context[key] = value
    profile["profile_completeness"] = _completeness(context)
    profile["updated_at"] = _now(); return profile


def update_self_report(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    by_key = {item["key"]: item for item in profile.get("general_states", []) if isinstance(item, dict)}
    for key, value in updates.items():
        if key in _SELF_REPORT_KEYS and value is not None:
            score = max(0, min(100, int(value))); state = by_key.get(key)
            if state: state.update({"self_report": score, "status": "assessed", "level": "\u7528\u6237\u81ea\u8bc4", "evidence": _evidence("user_self_report", f"\u7528\u6237\u81ea\u8bc4 {score}/100", []), "updated_at": _now()})
    profile["updated_at"] = _now(); return profile


def assess_interest(profile: dict[str, Any], answers: list[int]) -> dict[str, Any]:
    values = [max(1, min(5, int(item))) for item in answers[:5]]
    if values:
        for state in profile.get("general_states", []):
            if state.get("key") == "interest": state.update({"status": "assessed", "system_estimate": round(sum(values) / len(values) * 20), "level": "\u5df2\u6821\u51c6", "confidence": "medium", "evidence": _evidence("interest_calibration", "\u5b8c\u6210\u5f53\u524d\u5b66\u79d1\u5174\u8da3\u6821\u51c6\u95ee\u7b54", []), "updated_at": _now()})
    profile["updated_at"] = _now(); return profile


INTEREST_QUESTIONS = ["\u6211\u89c9\u5f97\u8fd9\u95e8\u8bfe\u7a0b\u7684\u5185\u5bb9\u503c\u5f97\u6295\u5165\u65f6\u95f4\u3002", "\u5373\u4f7f\u6ca1\u6709\u8003\u8bd5\uff0c\u6211\u4e5f\u613f\u610f\u7ee7\u7eed\u4e86\u89e3\u5176\u4e2d\u7684\u5185\u5bb9\u3002", "\u6211\u613f\u610f\u4e3a\u8fd9\u95e8\u8bfe\u7a0b\u4e3b\u52a8\u5b8c\u6210\u989d\u5916\u7ec3\u4e60\u3002"]
