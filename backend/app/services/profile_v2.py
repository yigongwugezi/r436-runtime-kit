"""Stable, explainable learner profile V2 built from existing JSON snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable

from app.services.profile_extractor import extract_profile_facts
from app.utils.profile_normalizer import detect_course_category


_CATEGORY_NAMES = {"cs": "computing", "math": "mathematics", "language": "language", "science": "physics"}
_DIMENSIONS = {
    "computing": [
        ("prerequisites", "\u5148\u4fee\u77e5\u8bc6"), ("concept_understanding", "\u6982\u5ff5\u7406\u89e3"),
        ("complexity_analysis", "\u590d\u6742\u5ea6\u5206\u6790"), ("algorithmic_thinking", "\u7b97\u6cd5\u601d\u7ef4"),
        ("code_implementation", "\u4ee3\u7801\u5b9e\u73b0"), ("debugging", "\u8c03\u8bd5\u80fd\u529b"),
    ],
    "mathematics": [
        ("basic_concepts", "\u57fa\u7840\u6982\u5ff5"), ("calculation", "\u8fd0\u7b97\u80fd\u529b"),
        ("formula_understanding", "\u516c\u5f0f\u7406\u89e3"), ("logical_reasoning", "\u903b\u8f91\u63a8\u5bfc"),
        ("proof_reasoning", "\u8bc1\u660e\u80fd\u529b"), ("modeling", "\u5e94\u7528\u5efa\u6a21"),
    ],
    "language": [
        ("vocabulary", "\u8bcd\u6c47"), ("grammar", "\u8bed\u6cd5"), ("reading", "\u9605\u8bfb"),
        ("listening", "\u542c\u529b"), ("writing", "\u5199\u4f5c"), ("speaking", "\u53e3\u8bed"),
    ],
    "physics": [
        ("concept_understanding", "\u6982\u5ff5\u7406\u89e3"), ("formula_application", "\u516c\u5f0f\u8fd0\u7528"),
        ("mathematical_reasoning", "\u6570\u5b66\u63a8\u5bfc"), ("physical_modeling", "\u7269\u7406\u5efa\u6a21"),
        ("experiment_understanding", "\u5b9e\u9a8c\u7406\u89e3"), ("integrated_problem_solving", "\u7efc\u5408\u89e3\u9898"),
    ],
    "general": [
        ("basic_knowledge", "\u57fa\u7840\u77e5\u8bc6"), ("concept_understanding", "\u6982\u5ff5\u7406\u89e3"),
        ("memory_mastery", "\u8bb0\u5fc6\u638c\u63e1"), ("analysis", "\u5206\u6790\u80fd\u529b"),
        ("application", "\u5e94\u7528\u80fd\u529b"), ("expression", "\u7efc\u5408\u8868\u8fbe"),
    ],
}
_STATE_LABELS = [("interest", "\u5f53\u524d\u5174\u8da3"), ("confidence", "\u5b66\u4e60\u4fe1\u5fc3"), ("engagement", "\u6295\u5165\u610f\u613f"), ("self_regulation", "\u81ea\u6211\u8c03\u8282"), ("pressure", "\u5f53\u524d\u538b\u529b")]
_CONTEXT_KEYS = {"learning_goal", "deadline", "daily_minutes", "prior_experience", "background", "content_preferences", "resource_preferences"}
_SELF_REPORT_KEYS = {key for key, _ in _STATE_LABELS}
_MISSING = {"", "\u5f85\u8865\u5145", "\u672a\u8bc4\u4f30", "\u672a\u77e5", "\u6682\u65e0", "none", "null", "undefined"}
_PREFERENCES = (("example_first", "\u5148\u770b\u4f8b\u9898"), ("practice_after_explanation", "\u8bb2\u89e3\u540e\u7ec3\u4e60"), ("definition_first", "\u5148\u8bb2\u5b9a\u4e49"), ("visual_explanation", "\u56fe\u89e3"), ("step_by_step", "\u5206\u6b65\u8bb2\u89e3"), ("concise_explanation", "\u7b80\u6d01\u8bb2\u89e3"))
_CONTEXT_FACTS = {
    "target_course": "subject_name", "learning_goal": "learning_goal", "deadline": "deadline", "time_budget": "deadline",
    "daily_minutes": "daily_minutes", "background": "background", "knowledge_base": "prior_experience",
    "prior_experience": "prior_experience", "content_preferences": "content_preferences", "preference": "content_preferences",
    "resource_preferences": "resource_preferences",
}
FACT_SCOPES = {"global", "subject", "course", "path", "session"}


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
    return str(value).strip().lower() in _MISSING or str(value).strip() == "\u8bc1\u636e\u4e0d\u8db3"


def _clean_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else re.split(r"[\u3001,\uff0c;\uff1b/]", str(value or ""))
    return list(dict.fromkeys(item.strip() for item in values if not _missing(item)))


def _prior_experience(value: Any, category: str) -> list[str]:
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
    return _number(match.group(1)) if match else None


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


def _confidence(source_type: str) -> str:
    return {"manual_edit": "high", "user_self_report": "high", "conversation_explicit": "high", "assessment": "high", "system_observation": "low"}.get(source_type, "medium")


def _evidence(source_type: str, detail: str, targets: list[str], *, session_id: str = "", subject_id: str = "", confidence: str | None = None) -> list[dict[str, Any]]:
    if _missing(detail):
        return []
    now = _now()
    return [{
        "source": source_type, "source_type": source_type, "detail": detail, "evidence_summary": detail,
        "target_keys": targets, "confidence": confidence or _confidence(source_type), "session_id": session_id,
        "subject_id": subject_id, "updated_at": now, "evidence_refs": [],
    }]


def _fact_record(
    value: Any,
    source_type: str,
    detail: str,
    *,
    fact_key: str = "",
    session_id: str = "",
    subject_id: str = "",
    confidence: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    now = _now()
    fact_type = {
        "conversation_explicit": "explicit", "manual_edit": "explicit",
        "user_self_report": "explicit", "system_observation": "observed",
        "inferred": "inferred", "system_default": "system_default",
    }.get(source_type, "explicit" if source_type in {"assessment", "user_input"} else "inferred")
    return {
        "fact_key": fact_key, "value": value, "normalized_value": value,
        "fact_type": fact_type, "source_type": source_type, "scope": scope or ("subject" if subject_id else "global"),
        "evidence_summary": detail, "evidence_refs": [],
        "confidence": confidence or _confidence(source_type), "session_id": session_id,
        "subject_id": subject_id, "first_observed_at": now, "last_observed_at": now,
        "last_confirmed_at": now if fact_type == "explicit" else None, "status": "active",
        "is_user_locked": source_type == "manual_edit", "is_disabled_for_personalization": False,
        "supersedes": None, "metadata": {}, "updated_at": now,
    }


def _category(course_name: str, course: dict[str, Any] | None) -> str:
    context = dict(course or {})
    context.setdefault("course_name", course_name)
    return _CATEGORY_NAMES.get(detect_course_category(context), "general")


def _dimension_map(dimensions: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {str(item.get("key")): item for item in dimensions or [] if isinstance(item, dict) and item.get("key")}


def _context(facts: dict[str, Any], legacy: dict[str, dict[str, Any]], course: dict[str, Any] | None, session_id: str = "") -> dict[str, Any]:
    course_name = str((course or {}).get("course_name") or facts.get("target_course") or legacy.get("interest_direction", {}).get("value") or "").strip()
    time_text = str(facts.get("time_budget") or legacy.get("learning_rhythm", {}).get("value") or "")
    preference = facts.get("content_preferences") or facts.get("preference") or legacy.get("cognitive_style", {}).get("value")
    resource_preferences = _clean_list(facts.get("resource_preferences"))
    if any(token in str(preference or "") for token in ("视频", "动画")) and "视频" not in resource_preferences:
        resource_preferences.append("视频")
    category = _category(course_name, course)
    return {
        "session_id": session_id, "subject_id": str((course or {}).get("course_id") or ""), "subject_name": course_name, "subject_category": category,
        "learning_goal": "" if _missing(facts.get("learning_goal")) else str(facts.get("learning_goal")).strip(),
        "deadline": _deadline(facts.get("deadline") or time_text), "daily_minutes": _minutes(facts.get("daily_minutes") or time_text),
        "prior_experience": _prior_experience(facts.get("prior_experience") or facts.get("knowledge_base"), category),
        "background": "" if _missing(facts.get("background")) else str(facts.get("background")).strip(), "language": "zh-CN",
        "content_preferences": _preferences(preference), "resource_preferences": resource_preferences,
    }


def _completeness(context: dict[str, Any]) -> float:
    values = (context.get("subject_name"), context.get("learning_goal"), context.get("daily_minutes") or context.get("deadline"), context.get("background"), context.get("prior_experience"), context.get("content_preferences"))
    return round(sum(not _missing(value) for value in values) / len(values), 2)


def _claims(facts: dict[str, Any]) -> list[str]:
    raw = "\uff1b".join(str(facts.get(key) or "") for key in ("weak_points", "knowledge_base", "prior_experience"))
    return list(dict.fromkeys(re.sub(r"^(?:\u4f46|\u6211|\u7684)", "", item).strip() for item in re.split(r"[,\uff0c;\uff1b\n]", raw) if not _missing(item)))


def _targets(claim: str, category: str) -> list[str]:
    text = claim.lower()
    if category == "computing":
        targets: list[str] = []
        if any(word in text for word in ("\u590d\u6742\u5ea6", "\u65f6\u95f4\u590d\u6742\u5ea6")): targets.append("complexity_analysis")
        if any(word in text for word in ("c\u8bed\u8a00", "python", "\u4ee3\u7801")): targets.append("prerequisites")
        if any(word in text for word in ("debug", "\u8c03\u8bd5", "\u62a5\u9519")): targets.append("debugging")
        if any(word in text for word in ("\u6570\u7ec4", "\u94fe\u8868", "\u6811", "\u6808", "\u961f\u5217", "\u9012\u5f52")): targets.extend(["prerequisites", "concept_understanding"])
        if "\u7b97\u6cd5" in text: targets.append("algorithmic_thinking")
        return list(dict.fromkeys(targets))
    if category == "mathematics":
        targets = []
        if any(word in text for word in ("\u6781\u9650", "\u5fae\u79ef\u5206", "\u516c\u5f0f")): targets.extend(["basic_concepts", "formula_understanding"])
        if any(word in text for word in ("\u8bc1\u660e", "\u63a8\u5bfc")): targets.extend(["logical_reasoning", "proof_reasoning"])
        return list(dict.fromkeys(targets))
    if category == "language":
        return [key for key, word in (("reading", "\u9605\u8bfb"), ("writing", "\u5199\u4f5c"), ("grammar", "\u8bed\u6cd5"), ("vocabulary", "\u8bcd\u6c47"), ("listening", "\u542c\u529b"), ("speaking", "\u53e3\u8bed")) if word in text]
    if category == "physics":
        return [key for key, word in (("concept_understanding", "\u6982\u5ff5"), ("formula_application", "\u516c\u5f0f"), ("mathematical_reasoning", "\u63a8\u5bfc"), ("physical_modeling", "\u5efa\u6a21"), ("experiment_understanding", "\u5b9e\u9a8c")) if word in text]
    return []


def _point_names(text: str) -> list[str]:
    cleaned = re.sub(r"(?:\u6bd4\u8f83|\u8f83)?\u8584\u5f31|\u4e0d\u592a\u4f1a|\u4e0d\u4f1a|\u4e0d\u61c2|\u57fa\u7840\u8fd8\u53ef\u4ee5|\u8fd8\u53ef\u4ee5", "", text)
    names = re.split(r"[\u3001,\uff0c;\uff1b\u548c\u4e0e\u53ca\u3001\s]+", cleaned)
    ignored = {"\u6211", "\u7684", "\u4f46", "\u6bd4\u8f83", "\u57fa\u7840", "\u77e5\u8bc6\u70b9"}
    return list(dict.fromkeys(name.strip("\u3002\uff0c,\uff1b;\uff1a: ") for name in names if 0 < len(name.strip()) <= 24 and name.strip() not in ignored))


def _knowledge(claims: list[str], category: str, *, session_id: str = "", subject_id: str = "") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        status = "weak" if any(token in claim for token in ("\u8584\u5f31", "\u4e0d\u4f1a", "\u4e0d\u61c2", "\u4e0d\u592a\u4f1a", "\u56f0\u96be")) else "familiar" if any(token in claim for token in ("\u8fd8\u53ef\u4ee5", "\u5b66\u8fc7", "\u64c5\u957f", "\u719f\u6089")) else "unknown"
        for name in _point_names(claim):
            if name in seen:
                continue
            seen.add(name)
            result.append({"knowledge_id": name, "label": name, "status": status, "confidence": "high", "evidence": _evidence("conversation_explicit", f"\u7528\u6237\u660e\u786e\u8868\u793a{name}{'\u6bd4\u8f83\u8584\u5f31' if status == 'weak' else '\u6709\u4e00\u5b9a\u57fa\u7840'}\u3002", _targets(claim, category), session_id=session_id, subject_id=subject_id), "updated_at": _now()})
    return result


def _states(existing: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    previous = {item.get("key"): item for item in (existing or {}).get("general_states", []) if isinstance(item, dict)}
    return [previous.get(key, {"key": key, "label": label, "status": "unassessed", "self_report": None, "system_estimate": None, "level": "\u672a\u8bc4\u4f30", "confidence": "low", "evidence": [], "updated_at": _now()}) for key, label in _STATE_LABELS]


def _refresh_profile(profile: dict[str, Any], facts: dict[str, Any] | None = None, weaknesses: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    context = profile.setdefault("subject_context", {})
    category = context.get("subject_category") or "general"
    claims = _claims(facts or {})
    prior = context.get("prior_experience") or []
    claims.extend(item for item in prior if item not in claims)
    old_mastery = {str(item.get("knowledge_id")): item for item in profile.get("knowledge_mastery", []) if isinstance(item, dict)}
    new_mastery = _knowledge(claims, category, session_id=str(context.get("session_id") or ""), subject_id=str(context.get("subject_id") or ""))
    for item in new_mastery:
        existing = old_mastery.get(item["knowledge_id"])
        if existing and existing.get("status") == "mastered":
            item = {**item, "status": "mastered", "confidence": existing.get("confidence", "medium"), "evidence": existing.get("evidence", item["evidence"])}
        old_mastery[item["knowledge_id"]] = item
    profile["knowledge_mastery"] = list(old_mastery.values())
    dimensions = []
    for key, label in _DIMENSIONS.get(category, _DIMENSIONS["general"]):
        matched = [item for item in profile["knowledge_mastery"] if key in _targets(str(item.get("label") or ""), category)]
        dimensions.append({"key": key, "label": label, "status": "tentative" if matched else "unassessed", "score": None, "confidence": "low" if not matched else "medium", "evidence": [evidence for item in matched for evidence in item.get("evidence", [])], "recommended_action": "\u5b8c\u6210\u9488\u5bf9\u672c\u9879\u7684\u7ec3\u4e60\u6216\u8bca\u65ad\u540e\u518d\u8bc4\u4f30\u3002", "updated_at": _now()})
    profile["subject_dimensions"] = dimensions
    profile["general_states"] = _states(profile)
    profile["profile_completeness"] = _completeness(context)
    profile["evidence_summary"] = {"conversation": sum(len(item.get("evidence", [])) for item in profile["knowledge_mastery"]), "diagnostic": len(weaknesses or []), "practice": 0, "behavior": 0}
    profile["updated_at"] = _now()
    return profile


def build_profile_v2(*, dimensions: list[dict[str, Any]] | None = None, facts: dict[str, Any] | None = None, course: dict[str, Any] | None = None, weaknesses: list[dict[str, Any]] | None = None, existing: dict[str, Any] | None = None, session_id: str = "") -> dict[str, Any]:
    facts, legacy = facts or {}, _dimension_map(dimensions)
    context = _context(facts, legacy, course, session_id)
    profile = dict(existing) if isinstance(existing, dict) and existing.get("profile_version") == 2 else {"profile_version": 2}
    previous = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
    records = profile.get("fact_records") if isinstance(profile.get("fact_records"), dict) else {}
    for key, record in records.items():
        if isinstance(record, dict):
            record.setdefault("fact_key", key)
            record.setdefault("normalized_value", record.get("value"))
            record.setdefault("fact_type", "explicit" if record.get("source_type") in {"conversation_explicit", "manual_edit", "user_self_report"} else "inferred")
            record.setdefault("scope", "subject" if record.get("subject_id") else "global")
            record.setdefault("status", "active")
            record.setdefault("is_user_locked", record.get("source_type") == "manual_edit")
            record.setdefault("is_disabled_for_personalization", False)
            record.setdefault("evidence_refs", [])
            record.setdefault("metadata", {})
    for key, value in previous.items():
        if key not in context or _missing(context.get(key)):
            context[key] = value
    for key, record in records.items():
        if isinstance(record, dict) and record.get("source_type") == "manual_edit" and key in context and not _missing(record.get("value")):
            context[key] = record["value"]
    profile["subject_context"] = context
    profile["fact_records"] = records
    for fact_key, context_key in _CONTEXT_FACTS.items():
        if fact_key in facts and not _missing(facts[fact_key]) and context_key not in records:
            profile["fact_records"][context_key] = _fact_record(context.get(context_key), "conversation_explicit", f"\u7528\u6237\u5728\u5bf9\u8bdd\u4e2d\u660e\u786e\u8868\u8fbe\u4e86{context_key}\u3002", fact_key=context_key, subject_id=str(context.get("subject_id") or ""))
    return _refresh_profile(profile, facts, weaknesses)


def _sync_candidates(messages: Iterable[Any], session_id: str, subject_id: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    context_values: dict[str, dict[str, Any]] = {}
    knowledge: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") if isinstance(message, dict) else getattr(message, "role", ""))
        content = str(message.get("content") if isinstance(message, dict) else getattr(message, "content", ""))
        if role != "user" or not content.strip():
            continue
        extracted = extract_profile_facts(content)
        for fact_key, value in extracted.facts.items():
            context_key = _CONTEXT_FACTS.get(fact_key)
            if not context_key:
                continue
            normalized = value
            if context_key == "daily_minutes": normalized = _minutes(value)
            elif context_key == "deadline": normalized = _deadline(value)
            elif context_key == "prior_experience": normalized = _clean_list(value)
            elif context_key == "content_preferences": normalized = _preferences(value)
            if _missing(normalized):
                continue
            context_values[context_key] = _fact_record(normalized, "conversation_explicit", f"\u7528\u6237\u5728\u5f53\u524d\u5bf9\u8bdd\u4e2d\u660e\u786e\u8868\u8fbe\u4e86{str(normalized)}\u3002", fact_key=context_key, session_id=session_id, subject_id=subject_id)
        for claim in (extracted.facts.get("weak_points", ""), extracted.facts.get("knowledge_base", ""), extracted.facts.get("prior_experience", "")):
            for item in _knowledge([claim], "computing", session_id=session_id, subject_id=subject_id):
                if item["knowledge_id"] not in {entry["knowledge_id"] for entry in knowledge}:
                    knowledge.append(item)
    return context_values, knowledge


def preview_conversation_sync(profile: dict[str, Any], messages: Iterable[Any], *, session_id: str, subject_id: str) -> dict[str, Any]:
    candidates, knowledge = _sync_candidates(messages, session_id, subject_id)
    current = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
    records = profile.get("fact_records") if isinstance(profile.get("fact_records"), dict) else {}
    added: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for key, candidate in candidates.items():
        old_value = current.get(key)
        if _missing(old_value):
            added.append({"field": key, "value": candidate["value"], "evidence": candidate})
        elif old_value == candidate["value"]:
            ignored.append({"field": key, "value": candidate["value"], "reason": "\u5df2\u7ecf\u5b58\u5728\u76f8\u540c\u4e8b\u5b9e"})
        elif isinstance(records.get(key), dict) and records[key].get("source_type") == "manual_edit":
            conflicts.append({"field": key, "current": old_value, "candidate": candidate["value"], "reason": "\u7528\u6237\u624b\u52a8\u786e\u8ba4\u7684\u503c\u4e0d\u4f1a\u88ab\u5bf9\u8bdd\u8986\u76d6"})
        else:
            updates.append({"field": key, "current": old_value, "value": candidate["value"], "evidence": candidate})
    existing_knowledge = {str(item.get("knowledge_id")) for item in profile.get("knowledge_mastery", []) if isinstance(item, dict)}
    for item in knowledge:
        if item["knowledge_id"] in existing_knowledge:
            ignored.append({"field": "knowledge_mastery", "value": item["label"], "reason": "\u77e5\u8bc6\u70b9\u5df2\u5b58\u5728"})
        else:
            added.append({"field": "knowledge_mastery", "value": item["label"], "evidence": item["evidence"][0]})
    return {"added": added, "updates": updates, "conflicts": conflicts, "ignored": ignored, "has_changes": bool(added or updates), "candidate_count": len(candidates) + len(knowledge)}


def apply_conversation_sync(profile: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    context = profile.setdefault("subject_context", {})
    records = profile.setdefault("fact_records", {})
    for item in [*preview.get("added", []), *preview.get("updates", [])]:
        field = str(item.get("field") or "")
        if field == "knowledge_mastery" or not field:
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        context[field] = evidence.get("value", item.get("value"))
        records[field] = evidence
    mastery = {str(item.get("knowledge_id")): item for item in profile.get("knowledge_mastery", []) if isinstance(item, dict)}
    for item in preview.get("added", []):
        if item.get("field") != "knowledge_mastery":
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        label = str(item.get("value") or "")
        if label and label not in mastery:
            mastery[label] = {"knowledge_id": label, "label": label, "status": "weak" if "\u8584\u5f31" in str(evidence.get("evidence_summary") or "") else "familiar", "confidence": evidence.get("confidence", "high"), "evidence": [evidence], "updated_at": _now()}
    profile["knowledge_mastery"] = list(mastery.values())
    return _refresh_profile(profile)


def update_context(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    context = profile.setdefault("subject_context", {})
    records = profile.setdefault("fact_records", {})
    for key, value in updates.items():
        if key not in _CONTEXT_KEYS:
            continue
        if key == "daily_minutes": value = _minutes(value)
        elif key in {"prior_experience", "resource_preferences"}: value = _clean_list(value)
        elif key == "content_preferences": value = _preferences(value)
        elif key == "deadline": value = _deadline(value)
        context[key] = value
        records[key] = _fact_record(value, "manual_edit", f"\u7528\u6237\u5728\u753b\u50cf\u9875\u624b\u52a8\u786e\u8ba4\u4e86{key}\u3002", fact_key=key, session_id=str(context.get("session_id") or ""), subject_id=str(context.get("subject_id") or ""))
    return _refresh_profile(profile)


def update_fact_control(profile: dict[str, Any], fact_key: str, action: str, value: Any = None, scope: str | None = None) -> dict[str, Any]:
    """Apply one user-visible fact control while retaining audit history."""
    if fact_key not in _CONTEXT_KEYS or (scope and scope not in FACT_SCOPES):
        raise ValueError("invalid profile fact scope")
    context = profile.setdefault("subject_context", {})
    records = profile.setdefault("fact_records", {})
    record = records.get(fact_key)
    if not isinstance(record, dict):
        record = _fact_record(context.get(fact_key), "manual_edit", f"用户确认了{fact_key}。", fact_key=fact_key, subject_id=str(context.get("subject_id") or ""))
    record.setdefault("fact_key", fact_key)
    if scope:
        record["scope"] = scope
    if action == "delete":
        record["status"] = "deleted"
        record["is_disabled_for_personalization"] = True
        context.pop(fact_key, None)
    elif action in {"disable", "enable"}:
        record["is_disabled_for_personalization"] = action == "disable"
        record["status"] = "active"
    elif action in {"lock", "unlock"}:
        record["is_user_locked"] = action == "lock"
    elif action == "edit":
        if value is None or _missing(value):
            raise ValueError("fact value required")
        old_value = record.get("value")
        context[fact_key] = value
        record = _fact_record(value, "manual_edit", f"用户修改了{fact_key}。", fact_key=fact_key, session_id=str(context.get("session_id") or ""), subject_id=str(context.get("subject_id") or ""), scope=scope or record.get("scope"))
        record["supersedes"] = old_value
    else:
        raise ValueError("unsupported profile fact action")
    records[fact_key] = record
    return _refresh_profile(profile)


def delete_fact(profile: dict[str, Any], fact_key: str) -> dict[str, Any]:
    return update_fact_control(profile, fact_key, "delete")


def set_fact_personalization(profile: dict[str, Any], fact_key: str, enabled: bool) -> dict[str, Any]:
    return update_fact_control(profile, fact_key, "enable" if enabled else "disable")


def personalization_context(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return the smallest safe profile slice used by search/generation."""
    profile = profile or {}
    context = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
    records = profile.get("fact_records") if isinstance(profile.get("fact_records"), dict) else {}
    result: dict[str, Any] = {}
    for key in ("subject_name", "prior_experience", "content_preferences", "resource_preferences", "learning_goal"):
        record = records.get(key) if isinstance(records.get(key), dict) else {}
        if record.get("status") == "active" and not record.get("is_disabled_for_personalization") and not _missing(context.get(key)):
            result[key] = context[key]
    return result


def record_behavior_fact(profile: dict[str, Any], fact_key: str, value: Any, *, subject_id: str = "") -> dict[str, Any]:
    """Accumulate weak observed evidence; one event never becomes a strong preference."""
    records = profile.setdefault("fact_records", {})
    record = records.get(fact_key)
    if not isinstance(record, dict) or record.get("fact_type") != "observed":
        record = _fact_record(value, "system_observation", "来自重复学习行为的系统观察。", fact_key=fact_key, subject_id=subject_id, confidence="low")
    metadata = record.setdefault("metadata", {})
    metadata["observation_count"] = int(metadata.get("observation_count", 0)) + 1
    if metadata["observation_count"] >= 3:
        record["confidence"] = "medium"
    record["last_observed_at"] = _now()
    records[fact_key] = record
    return _refresh_profile(profile)


def update_self_report(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    by_key = {item["key"]: item for item in profile.get("general_states", []) if isinstance(item, dict)}
    for key, value in updates.items():
        if key in _SELF_REPORT_KEYS and value is not None and key in by_key:
            score = max(0, min(100, int(value)))
            by_key[key].update({"self_report": score, "status": "assessed", "level": "\u7528\u6237\u81ea\u8bc4", "confidence": "high", "evidence": _evidence("user_self_report", f"\u7528\u6237\u81ea\u8bc4 {score}/100", []), "updated_at": _now()})
    profile["general_states"] = list(by_key.values()); profile["updated_at"] = _now(); return profile


def assess_interest(profile: dict[str, Any], answers: list[int]) -> dict[str, Any]:
    values = [max(1, min(5, int(item))) for item in answers[:5]]
    if values:
        for state in profile.get("general_states", []):
            if state.get("key") == "interest":
                state.update({"status": "assessed", "system_estimate": round(sum(values) / len(values) * 20), "level": "\u5df2\u6821\u51c6", "confidence": "medium", "evidence": _evidence("assessment", "\u5b8c\u6210\u5f53\u524d\u5b66\u79d1\u5174\u8da3\u6821\u51c6\u95ee\u7b54", []), "updated_at": _now()})
    profile["updated_at"] = _now(); return profile


INTEREST_QUESTIONS = ["\u6211\u89c9\u5f97\u8fd9\u95e8\u8bfe\u7a0b\u7684\u5185\u5bb9\u503c\u5f97\u6295\u5165\u65f6\u95f4\u3002", "\u5373\u4f7f\u6ca1\u6709\u8003\u8bd5\uff0c\u6211\u4e5f\u613f\u610f\u7ee7\u7eed\u4e86\u89e3\u5176\u4e2d\u7684\u5185\u5bb9\u3002", "\u6211\u613f\u610f\u4e3a\u8fd9\u95e8\u8bfe\u7a0b\u4e3b\u52a8\u5b8c\u6210\u989d\u5916\u7ec3\u4e60\u3002"]
