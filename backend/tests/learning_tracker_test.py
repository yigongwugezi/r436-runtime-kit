import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.learning_tracker import LearningTracker  # noqa: E402


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(value, label: str) -> None:
    if not value:
        raise AssertionError(label)


def main() -> None:
    tracker = LearningTracker()
    tracker.log({"event": "resource_view", "resourceId": "res_lecture_001", "duration": 20}, session_id="s1")
    tracker.log({"event": "resource_complete", "resourceId": "res_lecture_001", "duration": 10}, session_id="s1")
    tracker.log(
        {
            "event": "quiz_result",
            "resourceId": "res_quiz_001",
            "duration": 15,
            "metadata": {"topic": "stack", "correct": 3, "total": 5, "wrong": 2},
        },
        session_id="s1",
    )
    tracker.log({"event": "practice_result", "resourceId": "res_practice", "duration": 30}, session_id="s1")
    tracker.log({"event": "resource_view", "resourceId": "res_other", "duration": 99}, session_id="s2")

    summary = tracker.summary("s1")
    assert_equal(summary["eventCount"], 4, "eventCount")
    assert_equal(summary["totalStudyMinutes"], 75, "totalStudyMinutes")
    assert_equal(summary["activeResourceCount"], 2, "activeResourceCount (practice_result excluded)")
    assert_equal(summary["viewedResources"], 1, "viewedResources")
    assert_equal(summary["completedResources"], 1, "completedResources")
    assert_equal(summary["practiceCount"], 1, "practiceCount")
    assert_equal(summary["quizAccuracy"], 60, "quizAccuracy")
    assert_equal(summary["weakTopics"][0]["topic"], "stack", "weak topic")
    recs = summary["recommendations"]
    assert_true(len(recs) >= 1, "recommendations should not be empty")
    rec = recs[0]
    assert_true("recommendation_type" in rec, "rec has recommendation_type")
    assert_true("title" in rec, "rec has title")
    assert_true("reason" in rec, "rec has reason")
    assert_true("priority" in rec, "rec has priority")
    assert_true("confidence" in rec, "rec has confidence")
    assert_true("evidence" in rec, "rec has evidence")
    assert_true("quality_status" in rec, "rec has quality_status")

    # Verify recentEvents in reverse chronological order
    recent = summary["recentEvents"]
    assert_true(len(recent) >= 2, "should have recent events")
    # Most recent event (practice_result) should be first
    assert_equal(recent[0]["event"], "practice_result", "newest event first")

    # ── Dedup tests ──────────────────────────────────────────────────
    # 1. Duplicate resource_complete for same (session, resource) → idempotent
    tracker.log(
        {"event": "resource_complete", "resourceId": "res_lecture_001", "duration": 5},
        session_id="s1",
    )
    summary_after_dedup = tracker.summary("s1")
    assert_equal(summary_after_dedup["completedResources"], 1,
                 "dedup: completedResources stays 1 after duplicate resource_complete")
    assert_equal(summary_after_dedup["eventCount"], 4,
                 "dedup: eventCount stays 4 after duplicate resource_complete skipped")

    # 2. Duplicate resource_view within time window → deduped (same session, same resource)
    tracker.log(
        {"event": "resource_view", "resourceId": "res_lecture_001"},
        session_id="s1",
    )
    summary_after_view_dedup = tracker.summary("s1")
    assert_equal(summary_after_view_dedup["viewedResources"], 1,
                 "dedup: viewedResources stays 1 after duplicate resource_view within window")
    assert_equal(summary_after_view_dedup["eventCount"], 4,
                 "dedup: eventCount stays 4 after duplicate resource_view skipped")

    # 3. quiz_result is NOT deduped — posting a second quiz_result should count both
    tracker.log(
        {"event": "quiz_result", "resourceId": "res_quiz_001",
         "metadata": {"topic": "stack", "correct": 5, "total": 5, "wrong": 0}},
        session_id="s1",
    )
    summary_after_quiz = tracker.summary("s1")
    assert_equal(summary_after_quiz["eventCount"], 5,
                 "dedup: eventCount is 5 after second quiz_result (NOT deduped)")
    assert_equal(summary_after_quiz["eventBreakdown"].get("quiz_result", 0), 2,
                 "dedup: quiz_result count is 2 (NOT deduped)")

    # 4. Event count consistency after dedup
    breakdown = summary_after_quiz["eventBreakdown"]
    assert_equal(summary_after_quiz["eventCount"], sum(breakdown.values()),
                 "dedup: eventCount == sum(breakdown) after dedup")

    # 5. Verify new analytics fields
    assert_true("latestQuizScore" in summary_after_quiz, "has latestQuizScore")
    assert_true("bestQuizScore" in summary_after_quiz, "has bestQuizScore")
    assert_true("feedbackStats" in summary_after_quiz, "has feedbackStats")
    # Since we have quiz results, latest/best should not be None
    assert_true(summary_after_quiz["latestQuizScore"] is not None, "latestQuizScore is populated")
    assert_true(summary_after_quiz["bestQuizScore"] is not None, "bestQuizScore is populated")
    assert_equal(summary_after_quiz["latestQuizScore"]["source"], "analytics",
                 "latestQuizScore has source")
    assert_equal(summary_after_quiz["bestQuizScore"]["quality_status"], "computed",
                 "bestQuizScore has quality_status")

    tracker.reset("s1")
    s1_after = tracker.summary("s1")
    assert_equal(s1_after["eventCount"], 0, "reset only s1")
    assert_equal(s1_after["viewedResources"], 0, "viewedResources after reset")
    assert_equal(s1_after["completedResources"], 0, "completedResources after reset")
    assert_equal(s1_after["practiceCount"], 0, "practiceCount after reset")
    assert_equal(tracker.summary("s2")["eventCount"], 1, "s2 remains")
    print("PASS learning_tracker_test")


if __name__ == "__main__":
    main()
