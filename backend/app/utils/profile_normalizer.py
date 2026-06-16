"""Profile dimension normalization utilities.

Maps old 8-dimension profile keys to the current 10-dimension format
expected by the frontend, and fills in missing default dimensions.
"""

from typing import Any

# Mapping from old (Stage 1) dimension keys to new (Stage 2) keys
OLD_TO_NEW_KEYS: dict[str, str] = {
    "weak_points": "error_patterns",
    "programming_ability": "coding_ability",
    "interests": "interest_direction",
}

# Default values for dimensions that may be missing from older snapshots
DEFAULT_DIMENSIONS: dict[str, dict[str, Any]] = {
    "learning_rhythm": {
        "label": "学习节奏",
        "value": "暂未确定",
        "confidence": 0.5,
        "source": "inferred",
        "evidence": "暂无数据",
    },
    "self_efficacy": {
        "label": "学习效能感",
        "value": "暂未确定",
        "confidence": 0.5,
        "source": "inferred",
        "evidence": "暂无数据",
    },
}


def normalize_profile_dimensions(
    dimensions: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalize dimensions from DB to frontend-expected 10-dimension format.

    Handles:
    - Old 8-dimension snapshots (remaps keys, adds missing)
    - New 10-dimension snapshots (pass-through)
    - Dict format (agent result) -> list format (DB format)
    """
    if dimensions is None:
        dimensions = []

    # Convert dict format to list format
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

    # Remap old keys and collect seen keys
    seen_keys: set[str] = set()
    result: list[dict[str, Any]] = []
    for dim in dimensions:
        if not isinstance(dim, dict):
            continue
        old_key = str(dim.get("key", ""))
        new_key = OLD_TO_NEW_KEYS.get(old_key, old_key)
        dim["key"] = new_key
        seen_keys.add(new_key)
        result.append(dim)

    # Add missing default dimensions
    for key, default in DEFAULT_DIMENSIONS.items():
        if key not in seen_keys:
            result.append({"key": key, **default})

    return result
