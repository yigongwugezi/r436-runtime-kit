"""Candidate history must not add runtime or generated artifacts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = (
    r"^backend/data/(memory|user|static/images)/",
    r"^(outputs|playwright-report|test-results|screenshots)/",
    r"(^|/)[^/]+\.(db|sqlite|log|cache|pptx|mp4)$",
    r"(^|/)\.env$",
    r"(^|/)[^/]+\.tsbuildinfo$",
)


def main() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    assert not any(re.search(pattern, path) for pattern in FORBIDDEN for path in tracked)
    print("repository hygiene: PASS")


if __name__ == "__main__":
    main()
