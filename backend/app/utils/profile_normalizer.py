"""Profile dimension normalization utilities."""

from __future__ import annotations

from typing import Any

PROFILE_DIMENSION_ORDER = [
    "major_background",
    "knowledge_base",
    "learning_goal",
    "cognitive_style",
    "error_patterns",
    "coding_ability",
    "learning_progress",
    "interest_direction",
    "learning_rhythm",
    "self_efficacy",
]

PROFILE_DIMENSION_LABELS: dict[str, str] = {
    "major_background": "专业背景",
    "knowledge_base": "知识基础",
    "learning_goal": "学习目标",
    "cognitive_style": "认知风格",
    "error_patterns": "易错模式",
    "coding_ability": "编程能力",
    "learning_progress": "学习进度",
    "interest_direction": "兴趣方向",
    "learning_rhythm": "学习节奏",
    "self_efficacy": "学习效能",
}

OLD_TO_NEW_KEYS: dict[str, str] = {
    "weak_points": "error_patterns",
    "programming_ability": "coding_ability",
    "interests": "interest_direction",
}

DEFAULT_DIMENSIONS: dict[str, dict[str, Any]] = {
    key: {
        "label": label,
        "value": "待补充",
        "score": 50,
        "confidence": 0.35,
        "explanation": "当前对话中还缺少足够信息，后续可继续补充。",
        "evidence": "",
        "source": "rule_based_fallback",
    }
    for key, label in PROFILE_DIMENSION_LABELS.items()
}


def clamp_score(value: Any, default: int = 50) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, number))


def clamp_confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def normalize_profile_dimensions(
    dimensions: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalize dimensions to the stable 10-dimension schema."""
    if dimensions is None:
        dimensions = []

    if isinstance(dimensions, dict):
        dims_list: list[dict[str, Any]] = []
        for key, value in dimensions.items():
            if isinstance(value, dict):
                dims_list.append({"key": key, **value})
            else:
                dims_list.append({"key": key, "value": str(value)})
        dimensions = dims_list
    elif not isinstance(dimensions, list):
        return []

    by_key: dict[str, dict[str, Any]] = {}
    for dim in dimensions:
        if not isinstance(dim, dict):
            continue
        old_key = str(dim.get("key", "")).strip()
        new_key = OLD_TO_NEW_KEYS.get(old_key, old_key)
        if new_key not in PROFILE_DIMENSION_LABELS:
            continue

        default = DEFAULT_DIMENSIONS[new_key]
        value_text = str(dim.get("value", default["value"])).strip() or default["value"]
        explanation = str(dim.get("explanation", "")).strip() or value_text
        evidence = str(dim.get("evidence", "")).strip()
        source = str(dim.get("source", default["source"])).strip() or default["source"]

        by_key[new_key] = {
            "key": new_key,
            "label": str(dim.get("label", default["label"])) or default["label"],
            "value": value_text,
            "score": clamp_score(dim.get("score"), default["score"]),
            "confidence": clamp_confidence(dim.get("confidence"), default["confidence"]),
            "explanation": explanation,
            "description": explanation,
            "evidence": evidence,
            "source": source,
        }

    normalized: list[dict[str, Any]] = []
    for key in PROFILE_DIMENSION_ORDER:
        if key in by_key:
            normalized.append(by_key[key])
            continue
        normalized.append(
            {
                "key": key,
                "description": DEFAULT_DIMENSIONS[key]["explanation"],
                **DEFAULT_DIMENSIONS[key],
            }
        )
    return normalized
