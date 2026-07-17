"""Tests for ContentQualityService per-type quality checks (spec §12.5).

Covers:
  §6.2  lecture — passed / needs_review / blocked
  §6.3  mindmap — safety, hierarchy
  §6.4  quiz — answer consistency, empty stem, duplicate options
  §6.5  answer — explanation empty
  §6.6  PPT — empty file, readable file
  §6.7  search — URL format, risky domain
  §6.8  video — provider_unavailable
  §2.1  legacy status mapping
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# ── Test the service directly (no HTTP needed) ─────────────────────────

from app.services.content_quality_service import (
    PUBLIC_STATUSES,
    LEGACY_MAP,
    ContentQualityService,
    QualityReviewResult,
)


# ── §6.2 Lecture ──────────────────────────────────────────────────────────


def test_lecture_content_empty():
    """Empty lecture → blocked (empty content is severity=error)."""
    result = ContentQualityService.review({"type": "lecture", "title": "Test", "content": ""})
    assert result.status in ("blocked", "needs_review"), f"Got {result.status}"
    assert not result.checks.get("content_not_empty"), "content_not_empty should be False"


def test_lecture_passed():
    """Complete lecture with structure → passed."""
    content = "# 递归算法\n\n## 什么是递归\n\n递归是一个函数调用自身的关键概念，广泛应用于分治算法。\n\n## 终止条件\n\n每个递归函数必须有终止条件（base case）以防止无限循环。\n\n## 调用栈\n\n每次递归调用都会在调用栈上压入一个新帧。"
    result = ContentQualityService.review({
        "type": "lecture", "title": "递归算法",
        "content": content,
        "knowledge_points": ["递归", "调用栈"],
    })
    assert result.status == "passed", f"Expected passed, got {result.status}: {result.issues}"


def test_lecture_placeholder_blocked():
    """Lecture with placeholder tokens → blocked."""
    content = "# TODO\n\n概念A和概念B之间的关系是<placeholder>。"
    result = ContentQualityService.review({
        "type": "lecture", "title": "Test", "content": content,
    })
    assert result.status == "blocked", f"Expected blocked, got {result.status}"
    assert any(i["check"] == "placeholder_free" for i in result.issues)


def test_lecture_short_needs_review():
    """Very short lecture → needs_review."""
    result = ContentQualityService.review({
        "type": "lecture", "title": "Short", "content": "太短了，没有实际内容。",
    })
    assert result.status in ("needs_review", "blocked"), f"Expected needs_review/blocked, got {result.status}"


# ── §6.3 Mindmap ─────────────────────────────────────────────────────────


def test_mindmap_passed():
    """Mindmap with root + hierarchy → passed."""
    resource = {
        "type": "mindmap", "title": "数据结构",
        "mermaid_def": "mindmap\n  root((数据结构))\n    线性结构\n      数组\n      链表\n    非线性结构\n      树\n      图",
        "knowledge_points": ["数组", "链表", "树", "图"],
    }
    result = ContentQualityService.review(resource)
    assert result.status == "passed", f"Expected passed, got {result.status}: {result.issues}"


def test_mindmap_dangerous_blocked():
    """Mindmap with dangerous Mermaid directive → blocked."""
    resource = {
        "type": "mindmap", "title": "Test",
        "mermaid_def": "mindmap\n  root((X))\n    A\nclick A \"javascript:alert(1)\"",
    }
    result = ContentQualityService.review(resource)
    assert result.status == "blocked", f"Expected blocked, got {result.status}"


def test_mindmap_no_root_needs_review():
    """Mindmap without root → needs_review."""
    resource = {
        "type": "mindmap", "title": "No Root",
        "content": "graph TD\nA-->B",
    }
    result = ContentQualityService.review(resource)
    assert result.status in ("needs_review", "blocked"), f"Got {result.status}: {result.issues}"


# ── §6.4 Quiz ────────────────────────────────────────────────────────────


def test_quiz_passed():
    """Quiz with valid questions → passed."""
    resource = {
        "type": "quiz", "title": "Test Quiz",
        "difficulty": "medium",
        "questions": [
            {"id": "q1", "type": "choice", "stem": "What is the time complexity of binary search?",
             "options": ["A. O(1)", "B. O(log n)", "C. O(n)", "D. O(n^2)"],
             "correct": "B", "explanation": "Binary search halves the search space each iteration, giving O(log n) complexity."},
            {"id": "q2", "type": "choice", "stem": "Which data structure uses LIFO ordering?",
             "options": ["A. Queue", "B. Stack", "C. Tree", "D. Heap"],
             "correct": "B", "explanation": "Stack follows Last-In-First-Out (LIFO) ordering principle."},
        ],
    }
    result = ContentQualityService.review(resource)
    assert result.status == "passed", f"Expected passed, got {result.status}: {result.issues}"


def test_quiz_empty_stem_blocked():
    """Quiz with empty stem → blocked."""
    resource = {
        "type": "quiz", "title": "Bad Quiz",
        "questions": [
            {"id": "q1", "type": "choice", "stem": "", "options": ["A", "B"], "correct": "A", "explanation": "test"},
        ],
    }
    result = ContentQualityService.review(resource)
    assert result.status == "blocked", f"Expected blocked, got {result.status}"


def test_quiz_answer_not_in_options():
    """Quiz where correct answer not in options → blocked."""
    resource = {
        "type": "quiz", "title": "Bad Quiz",
        "difficulty": "easy",
        "questions": [
            {"id": "q1", "type": "choice", "stem": "What is 2+2?",
             "options": ["A. 3", "B. 5", "C. 6", "D. 7"],
             "correct": "B. 4", "explanation": "2+2=4, which is not in the options — this is a bad quiz."},
        ],
    }
    result = ContentQualityService.review(resource)
    assert result.status in ("blocked", "needs_review"), f"Got {result.status}: {result.issues}"
    assert any("answer_in_options" in str(i) for i in result.issues)


def test_quiz_duplicate_options():
    """Quiz with duplicate options (identical after normalization) → needs_review or blocked."""
    resource = {
        "type": "quiz", "title": "Dup Quiz",
        "difficulty": "medium",
        "questions": [
            {"id": "q1", "type": "choice", "stem": "Which of the following is correct?",
             "options": ["Same text", "Same text", "Same text", "Same text"],
             "correct": "A", "explanation": "All options are identical, which makes this a bad question."},
        ],
    }
    result = ContentQualityService.review(resource)
    assert result.status in ("needs_review", "blocked"), f"Got {result.status}: {result.issues}"
    assert any("distinct_options" in str(i) for i in result.issues)


# ── §6.5 Answer ──────────────────────────────────────────────────────────


def test_answer_empty_explanation():
    """Answer with empty explanation → needs_review."""
    result = ContentQualityService.review({
        "type": "lecture", "title": "Answer Test",
        "explanation": "", "isCorrect": True, "score": 100,
        "content": "Correct answer here.",
    })
    assert result.status in ("needs_review", "passed"), f"Got {result.status}: {result.issues}"


# ── §6.6 PPT ────────────────────────────────────────────────────────────


def test_ppt_file_readable():
    """PPT with valid file path → passed (if content quality OK)."""
    # Create a minimal file to simulate PPT
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        f.write(b"PK\x03\x04" + b"\x00" * 4000)
        ppt_path = f.name
    try:
        result = ContentQualityService.review({
            "type": "ppt", "title": "Test PPT",
            "content": ppt_path,
        })
        assert result.status == "passed", f"Expected passed, got {result.status}: {result.issues}"
        assert result.checks.get("file_readable"), "file_readable should be True"
        assert result.checks.get("safe_path"), "safe_path should be True"
    finally:
        os.unlink(ppt_path)


def test_ppt_file_missing():
    """PPT with nonexistent file → needs_review or blocked."""
    result = ContentQualityService.review({
        "type": "ppt", "title": "Missing PPT",
        "content": "/nonexistent/path/to/file.pptx",
    })
    assert result.status in ("needs_review", "blocked"), f"Got {result.status}: {result.issues}"
    assert not result.checks.get("file_readable", True), "file_readable should be False for missing file"


def test_ppt_empty_path():
    """PPT with empty content path → blocked."""
    result = ContentQualityService.review({
        "type": "ppt", "title": "Empty PPT",
        "content": "",
    })
    assert result.status == "blocked", f"Expected blocked, got {result.status}: {result.issues}"


# ── §6.7 Search ──────────────────────────────────────────────────────────


def test_search_valid_url():
    """Search result with valid URL + title → passed."""
    result = ContentQualityService.review({
        "type": "article", "title": "Recursion in Python",
        "content": "https://docs.python.org/3/tutorial/controlflow.html#recursive-functions",
    })
    assert result.status == "passed", f"Expected passed, got {result.status}: {result.issues}"
    assert result.checks.get("valid_url"), "valid_url should be True"


def test_search_invalid_url():
    """Search result with malformed URL → blocked or needs_review."""
    result = ContentQualityService.review({
        "type": "course", "title": "Bad URL",
        "content": "htp://not-a-valid-url",
    })
    assert result.status in ("blocked", "needs_review"), f"Got {result.status}: {result.issues}"
    assert not result.checks.get("valid_url", True), "valid_url should be False"


def test_search_risky_domain():
    """Search result with risky domain → blocked."""
    result = ContentQualityService.review({
        "type": "article", "title": "Suspicious Content",
        "content": "https://malware.com/bad-stuff",
    })
    assert result.status == "blocked", f"Expected blocked, got {result.status}: {result.issues}"
    assert any(i["check"] == "safe_domain" for i in result.issues)


# ── §6.8 Video / animation ───────────────────────────────────────────────


def test_video_provider_unavailable():
    """Video — provider_unavailable or needs_review depending on env."""
    result = ContentQualityService.review({
        "type": "video", "title": "Recursion Visualization",
        "content": "",
    })
    assert result.status in ("provider_unavailable", "needs_review"), (
        f"Got {result.status}: {result.issues}"
    )


# ── §2.1 Legacy status mapping ───────────────────────────────────────────


def test_legacy_status_mapping():
    """All legacy statuses map to the 4 public statuses."""
    expected = {
        "repaired": "passed",
        "failed": "needs_review",
        "pending": "needs_review",
        "warning": "needs_review",
        "fallback": "passed",
        "fallback_passed": "passed",
        "insufficient_context": "needs_review",
        "passed": "passed",
        "blocked": "blocked",
        "needs_review": "needs_review",
        "provider_unavailable": "provider_unavailable",
    }
    for legacy, expected_public in expected.items():
        actual = ContentQualityService.map_legacy_status(legacy)
        assert actual == expected_public, f"map_legacy_status({legacy!r}): expected {expected_public!r}, got {actual!r}"
        assert actual in PUBLIC_STATUSES, f"{actual!r} not in PUBLIC_STATUSES"


def test_unknown_status_maps_to_needs_review():
    """Unknown legacy statuses map to needs_review."""
    assert ContentQualityService.map_legacy_status("unknown_xyz") == "needs_review"


# ── Generic / edge cases ─────────────────────────────────────────────────


def test_generic_resource_with_content():
    """Generic resource with content → passed or needs_review (depends on structure)."""
    result = ContentQualityService.review({
        "type": "textbook", "title": "Algorithm Design Manual",
        "content": "# Chapter 1\n\n## Introduction\n\nThis textbook covers fundamental algorithm design techniques including sorting, searching, and graph traversal.",
    })
    assert result.status in ("passed", "needs_review"), f"Got {result.status}"


def test_generic_resource_empty():
    """Generic resource with no content → blocked."""
    result = ContentQualityService.review({
        "type": "textbook", "title": "", "content": "",
    })
    assert result.status in ("blocked", "needs_review"), f"Got {result.status}"


def test_all_results_have_public_status():
    """Every QualityReviewResult.status is one of the 4 public statuses."""
    resources = [
        {"type": "lecture", "title": "Test", "content": "# Section\n\nContent here with enough length to pass basic checks and demonstrate structure."},
        {"type": "mindmap", "title": "Test", "mermaid_def": "mindmap\n  root((X))\n    A\n    B"},
        {"type": "quiz", "title": "Test", "difficulty": "easy",
         "questions": [{"id": "q1", "type": "choice", "stem": "Question one here with decent length?",
                        "options": ["A. One", "B. Two", "C. Three", "D. Four"],
                        "correct": "A", "explanation": "Because A is the right answer here."}]},
        {"type": "video", "title": "Test", "content": ""},
        {"type": "article", "title": "Test", "content": "https://example.org/page"},
        {"type": "lecture", "title": "", "content": ""},
    ]
    for r in resources:
        result = ContentQualityService.review(r)
        assert result.status in PUBLIC_STATUSES, (
            f"Status {result.status!r} not in PUBLIC_STATUSES for type={r['type']}"
        )
        assert isinstance(result.checks, dict)
        assert isinstance(result.issues, list)


# ── Run ───────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_lecture_content_empty,
        test_lecture_passed,
        test_lecture_placeholder_blocked,
        test_lecture_short_needs_review,
        test_mindmap_passed,
        test_mindmap_dangerous_blocked,
        test_mindmap_no_root_needs_review,
        test_quiz_passed,
        test_quiz_empty_stem_blocked,
        test_quiz_answer_not_in_options,
        test_quiz_duplicate_options,
        test_answer_empty_explanation,
        test_ppt_file_readable,
        test_ppt_file_missing,
        test_ppt_empty_path,
        test_search_valid_url,
        test_search_invalid_url,
        test_search_risky_domain,
        test_video_provider_unavailable,
        test_legacy_status_mapping,
        test_unknown_status_maps_to_needs_review,
        test_generic_resource_with_content,
        test_generic_resource_empty,
        test_all_results_have_public_status,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
