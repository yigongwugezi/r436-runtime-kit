"""Canonical ID generation for the 5-level learning content hierarchy.

All IDs are deterministic from parent + index, ensuring stability across
regenerations and page refreshes.

Hierarchy:  path → stage → chapter → section → knowledge_point
"""

from __future__ import annotations


def make_path_id(session_id: str) -> str:
    """Generate a stable learning path ID from a session ID."""
    return f"path_{session_id}"


def make_stage_id(path_id: str, index: int) -> str:
    """Generate a stable stage ID.

    Args:
        path_id: The parent learning path ID.
        index: 0-based stage index within the path.
    """
    return f"{path_id}_s{index}"


def make_task_id(stage_id: str, index: int) -> str:
    """Generate a stable task ID.

    Args:
        stage_id: The parent stage ID.
        index: 0-based task index within the stage.
    """
    return f"{stage_id}_t{index}"


def make_chapter_id(stage_id: str, index: int) -> str:
    """Generate a stable chapter ID.

    Args:
        stage_id: The parent stage ID.
        index: 0-based chapter index within the stage.
    """
    return f"{stage_id}_ch{index}"


def make_section_id(chapter_id: str, index: int) -> str:
    """Generate a stable section ID.

    Args:
        chapter_id: The parent chapter ID.
        index: 0-based section index within the chapter.
    """
    return f"{chapter_id}_sec{index}"


def make_kp_id(section_id: str, index: int) -> str:
    """Generate a stable knowledge point ID.

    Args:
        section_id: The parent section ID.
        index: 0-based knowledge point index within the section.
    """
    return f"{section_id}_kp{index}"


def parse_id(id_str: str) -> dict[str, str]:
    """Parse a canonical ID back into its hierarchical components.

    Returns a dict with keys present at each level (path_id, stage_index,
    chapter_index, section_index, kp_index).  Absent levels are omitted.

    Example:
        parse_id("path_abc_s0_ch1_sec2_kp3")
        → {"path_id": "path_abc", "stage_index": "0", "chapter_index": "1",
           "section_index": "2", "kp_index": "3"}
    """
    result: dict[str, str] = {}
    parts = id_str.split("_")

    # path_id is everything before the first "_s"
    for i, part in enumerate(parts):
        if part.startswith("s") and len(part) > 1 and part[1:].isdigit():
            result["path_id"] = "_".join(parts[:i]) if i > 0 else parts[0]
            result["stage_index"] = part[1:]
            continue
        if part.startswith("ch") and len(part) > 2 and part[2:].isdigit():
            result["chapter_index"] = part[2:]
            continue
        if part.startswith("sec") and len(part) > 3 and part[3:].isdigit():
            result["section_index"] = part[3:]
            continue
        if part.startswith("kp") and len(part) > 2 and part[2:].isdigit():
            result["kp_index"] = part[2:]
            continue

    # Fallback: if we didn't find any structured parts, treat the whole thing as path_id
    if "path_id" not in result:
        result["path_id"] = id_str

    return result
