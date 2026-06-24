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
