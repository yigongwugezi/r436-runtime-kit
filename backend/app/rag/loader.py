"""NDJSON data loader for Chinese Wikipedia dump files.

Reads the directory tree::

    data_path/
      AA/
        wiki_00   (NDJSON, one JSON object per line)
        wiki_01
        ...
      AB/
        wiki_00
        ...

Each line is a flat JSON object with keys: ``id``, ``title``, ``text``, ``url``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.rag.loader")


def discover_files(data_path: str | Path) -> list[Path]:
    """Scan *data_path* for ``wiki_*`` NDJSON files across all subdirectories.

    Returns an absolute, sorted list of file paths.
    """
    root = Path(data_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Data directory not found: {root}")

    files: list[Path] = []
    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            for entry in sorted(sub.iterdir()):
                if entry.is_file() and entry.name.startswith("wiki_"):
                    files.append(entry)
    return files


def read_ndjson(file_path: Path) -> list[dict[str, Any]]:
    """Parse a single NDJSON file.

    Silently skips non-decodable lines (malformed JSON) and logs a warning.
    """
    records: list[dict[str, Any]] = []
    with open(file_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                records.append(obj)
            except json.JSONDecodeError:
                logger.warning(
                    "%s:%d — skipping malformed JSON line",
                    file_path.name,
                    lineno,
                )
    return records


def filter_empty_text(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove records whose ``text`` field is empty or whitespace-only.

    About 26 % of the Chinese Wikipedia test dataset has empty text
    (stubs, disambiguation pages, etc.).
    """
    kept = []
    removed = 0
    for r in records:
        text = (r.get("text") or "").strip()
        if text:
            kept.append(r)
        else:
            removed += 1
    if removed:
        logger.info("Filtered %d records with empty text", removed)
    return kept


def deduplicate_by_id(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the first occurrence of each ``id``."""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    duplicates = 0
    for r in records:
        rid = r.get("id", "")
        if rid in seen:
            duplicates += 1
            continue
        seen.add(rid)
        deduped.append(r)
    if duplicates:
        logger.info("Removed %d duplicate records by id", duplicates)
    return deduped


def load_all_records(
    data_path: str | Path,
    max_records: int = 0,
) -> list[dict[str, Any]]:
    """Load, filter and deduplicate all NDJSON files under *data_path*.

    Parameters:
        data_path: Root directory containing ``AA/``, ``AB/``, …
        max_records: If > 0, stop loading after this many valid records
                     (useful for quick smoke tests).

    Returns:
        List of clean record dicts with keys ``id``, ``title``, ``text``, ``url``.
    """
    files = discover_files(data_path)
    logger.info("Found %d wiki_* file(s) under %s", len(files), data_path)

    all_records: list[dict[str, Any]] = []
    for fp in files:
        records = read_ndjson(fp)
        logger.debug("  %s → %d records", fp.name, len(records))
        all_records.extend(records)

    logger.info("Total raw records loaded: %d", len(all_records))

    all_records = filter_empty_text(all_records)
    all_records = deduplicate_by_id(all_records)

    if max_records and max_records > 0:
        all_records = all_records[:max_records]
        logger.info("Capped at %d records (max_records)", max_records)

    logger.info("Final record count after cleaning: %d", len(all_records))
    return all_records
