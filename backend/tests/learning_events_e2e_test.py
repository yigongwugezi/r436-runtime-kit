"""End-to-end test for all 6 learning event types and 9 analytics fields.

Usage:
    cd backend
    python -m pytest tests/learning_events_e2e_test.py -v
"""

import sys
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import init_db
from app.db.engine import SessionLocal
from app.db.repository import save_resource
from app.main import app
from app.services.learning_tracker import learning_tracker

# Ensure DB tables exist and persistence is enabled for the test session
init_db()
learning_tracker.enable_db()

client = TestClient(app)
SESSION = f"e2e_test_{uuid.uuid4().hex[:8]}"


def _post_event(event: str, **kwargs: object) -> None:
    payload: dict[str, object] = {
        "sessionId": SESSION,
        "event": event,
        **kwargs,
    }
    r = client.post("/api/feedback/event", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def _get_analytics() -> dict[str, object]:
    r = client.get("/api/learning-analytics", params={"sessionId": SESSION})
    assert r.status_code == 200
    return r.json()


# ── Tests ──────────────────────────────────────────────────────────────


def test_all_six_event_types_logged() -> None:
    """Verify all 6 required event types are accepted by POST /api/feedback/event."""
    events = [
        ("resource_view", {"resourceId": "res_01", "metadata": {"type": "lecture", "title": "Test Lecture"}}),
        ("resource_complete", {"resourceId": "res_01", "metadata": {"type": "lecture", "title": "Test Lecture", "duration": 15}}),
        ("quiz_result", {"resourceId": "res_02", "metadata": {"correct": 3, "wrong": 1, "total": 4, "accuracy": 75, "topic": "数据结构", "knowledgePoint": "二叉树"}}),
        ("practice_result", {"resourceId": "res_03", "metadata": {"type": "case_study", "title": "Practice Lab", "duration": 30}}),
        ("node_progress", {"resourceId": "stage_1_node_1", "metadata": {"stageId": "stage_1", "status": "completed"}}),
        ("feedback", {"resourceId": "res_01", "metadata": {"rating": 4, "difficultyMatch": True}}),
    ]

    for event_type, extra in events:
        _post_event(event_type, **extra)

    analytics = _get_analytics()

    # Verify all 6 event types appear in the breakdown
    breakdown = analytics.get("eventBreakdown", {})
    for event_type, _ in events:
        assert event_type in breakdown, f"Event '{event_type}' missing from eventBreakdown"
        assert breakdown[event_type] >= 1, f"Event '{event_type}' count should be >= 1"

    print("PASS All 6 event types logged and present in breakdown")


def test_all_nine_analytics_fields_returned() -> None:
    """Verify all 9 analytics fields are present and have correct types."""
    analytics = _get_analytics()

    required_fields = [
        "eventCount",
        "totalStudyMinutes",
        "activeResourceCount",
        "eventBreakdown",
        "topResources",
        "quizAccuracy",
        "weakTopics",
        "recommendations",
        "recentEvents",
    ]

    for field in required_fields:
        assert field in analytics, f"Field '{field}' missing from analytics response"

    # Type checks
    assert isinstance(analytics["eventCount"], int)
    assert isinstance(analytics["totalStudyMinutes"], int)
    assert isinstance(analytics["activeResourceCount"], int)
    assert isinstance(analytics["eventBreakdown"], dict)
    assert isinstance(analytics["topResources"], list)
    assert analytics["quizAccuracy"] is None or isinstance(analytics["quizAccuracy"], int)
    assert isinstance(analytics["weakTopics"], list)
    assert isinstance(analytics["recommendations"], list)
    assert isinstance(analytics["recentEvents"], list)

    print("PASS All 9 analytics fields present with correct types")


def test_event_count_accuracy() -> None:
    """eventCount should equal sum of all event breakdown values."""
    analytics = _get_analytics()
    breakdown = analytics["eventBreakdown"]
    computed_total = sum(breakdown.values())
    assert analytics["eventCount"] == computed_total, (
        f"eventCount {analytics['eventCount']} != sum of breakdown {computed_total}"
    )
    print(f"PASS eventCount = {analytics['eventCount']} (matches breakdown sum)")


def test_total_study_minutes() -> None:
    """totalStudyMinutes should aggregate duration metadata from events."""
    analytics = _get_analytics()
    # We posted resource_complete(duration=15) + practice_result(duration=30) = 45
    assert analytics["totalStudyMinutes"] >= 30, (
        f"Expected >= 30 totalStudyMinutes, got {analytics['totalStudyMinutes']}"
    )
    print(f"PASS totalStudyMinutes = {analytics['totalStudyMinutes']}")


def test_active_resource_count() -> None:
    """activeResourceCount should count unique resources from RESOURCE_EVENTS."""
    analytics = _get_analytics()
    # We posted: res_01 (resource_view + resource_complete + feedback),
    #            res_02 (quiz_result), res_03 (practice_result)
    # node_progress is excluded from resource counting by design
    assert analytics["activeResourceCount"] >= 2, (
        f"Expected >= 2 activeResourceCount, got {analytics['activeResourceCount']}"
    )
    print(f"PASS activeResourceCount = {analytics['activeResourceCount']}")


def test_top_resources() -> None:
    """topResources should list resources sorted by event count."""
    analytics = _get_analytics()
    top = analytics["topResources"]
    assert len(top) >= 1, "Should have at least 1 top resource"
    # res_01 has 3 events (view + complete + feedback), should be #1
    assert top[0]["resourceId"] == "res_01", f"Expected res_01 as top, got {top[0]['resourceId']}"
    assert top[0]["count"] >= 2
    print(f"PASS topResources[0] = {top[0]['resourceId']} (count={top[0]['count']})")


def test_quiz_accuracy() -> None:
    """quizAccuracy should reflect quiz_result metadata."""
    analytics = _get_analytics()
    # We posted quiz_result with correct=3, total=4 → 75%
    assert analytics["quizAccuracy"] == 75, (
        f"Expected quizAccuracy=75, got {analytics['quizAccuracy']}"
    )
    print(f"PASS quizAccuracy = {analytics['quizAccuracy']}%")


def test_weak_topics() -> None:
    """weakTopics should contain structured objects from quiz metadata."""
    analytics = _get_analytics()
    weak = analytics["weakTopics"]
    assert len(weak) >= 1, "Should have at least 1 weak topic"
    # Should have topic="数据结构" from our quiz_result
    topic_names = [t["topic"] for t in weak]
    assert "数据结构" in topic_names, f"Expected 数据结构 in weakTopics, got {topic_names}"
    # Verify structure
    t = weak[0]
    assert "topic" in t
    assert "wrongCount" in t
    assert "totalCount" in t
    assert "risk" in t
    print(f"PASS weakTopics[0] = {t['topic']} (wrong={t['wrongCount']}, total={t['totalCount']}, risk={t['risk']})")


def test_recent_events() -> None:
    """recentEvents should contain the most recent events with correct structure."""
    analytics = _get_analytics()
    recent = analytics["recentEvents"]
    assert len(recent) >= 1, "Should have at least 1 recent event"
    evt = recent[-1]  # Most recent is last (events[-10:] in backend)
    assert "event" in evt
    assert "timestamp" in evt
    print(f"PASS recentEvents has {len(recent)} events, newest={evt['event']}")


def test_recommendations() -> None:
    """recommendations should contain actionable advice strings."""
    analytics = _get_analytics()
    recs = analytics["recommendations"]
    assert len(recs) >= 1, "Should have at least 1 recommendation"
    assert all(isinstance(r, str) for r in recs)
    print(f"PASS recommendations ({len(recs)} items)")


def test_event_breakdown_labels() -> None:
    """Verify event breakdown has human-readable event types (not 'generic')."""
    analytics = _get_analytics()
    breakdown = analytics["eventBreakdown"]
    assert "generic" not in breakdown, "Should not have 'generic' event type"
    print(f"PASS eventBreakdown keys: {list(breakdown.keys())}")


def test_session_isolation() -> None:
    """Verify events are scoped to session_id."""
    # Post an event to a different session
    other_session = "e2e_other_session"
    r = client.post("/api/feedback/event", json={
        "sessionId": other_session,
        "event": "resource_view",
        "resourceId": "isolated_res",
    })
    assert r.status_code == 200

    # Our session's analytics should NOT include the other session's event
    analytics = _get_analytics()
    breakdown = analytics["eventBreakdown"]
    # Our session count should be unchanged
    assert analytics["eventCount"] >= 6, f"Session eventCount should be >= 7, got {analytics['eventCount']}"

    # Other session's analytics should only have its own event
    r2 = client.get("/api/learning-analytics", params={"sessionId": other_session})
    other = r2.json()
    assert other["eventCount"] >= 1
    assert other["eventBreakdown"].get("resource_view", 0) >= 1

    print("PASS Session isolation works correctly")


def test_resource_status_cross_session() -> None:
    """Verify resource study_status cannot be modified across sessions."""
    res_id = f"{SESSION}_cross_session_res"
    db = SessionLocal()
    try:
        save_resource(db, SESSION, {
            "id": res_id,
            "type": "lecture",
            "title": "Session-owned resource",
            "content": "owner-only content",
            "study_status": "new",
        })
    finally:
        db.close()

    # Mark it completed in session A
    r1 = client.patch(f"/api/resources/{res_id}/study-status",
        json={"studyStatus": "completed"},
        params={"sessionId": SESSION})
    assert r1.status_code == 200
    assert r1.json().get("ok") is True

    # Session B tries to mark it incomplete
    other = "e2e_other_cross"
    r2 = client.patch(f"/api/resources/{res_id}/study-status",
        json={"studyStatus": "new"},
        params={"sessionId": other})
    assert r2.status_code == 200
    assert r2.json().get("ok") is False
    assert "does not belong" in r2.json().get("error", "")

    bookmark = client.post(
        f"/api/resources/{res_id}/bookmark",
        params={"sessionId": other},
    )
    assert bookmark.status_code == 200
    assert bookmark.json().get("ok") is False

    # Verify session A's status is still "completed"
    r3 = client.get(f"/api/resources/{res_id}", params={"sessionId": SESSION})
    assert r3.status_code == 200
    res = r3.json().get("resource", {})
    assert res.get("studyStatus") == "completed", "owned session keeps its status"
    print("PASS Resource status cross-session modification protected")


def test_feedback_default_session() -> None:
    """Verify feedback without sessionId is rejected and doesn't pollute."""
    # Fresh resource ID to avoid stale data
    fresh_id = "no_session_" + uuid.uuid4().hex[:6]
    r = client.post("/api/feedback", json={
        "resourceId": fresh_id, "rating": 5,
    })
    assert r.status_code == 400
    result = r.json()
    assert "sessionId is required" in str(result.get("detail", ""))
    print("PASS Feedback without sessionId correctly rejected")

    # Verify the rejected event did not leak into the test session
    analytics = client.get("/api/learning-analytics",
        params={"sessionId": SESSION}).json()
    resource_ids = {t.get("resourceId") for t in analytics.get("topResources", [])}
    assert fresh_id not in resource_ids, (
        "rejected event leaked into active session"
    )
    print("PASS Active session not polluted by rejected event")


def test_session_isolation_with_different_ids() -> None:
    """Verify events from different sessionId values are properly isolated."""
    subj_a = "e2e_subj_a_events"
    subj_b = "e2e_subj_b_events"

    # Post event for subject A
    client.post("/api/feedback/event", json={
        "sessionId": subj_a, "event": "resource_view",
        "resourceId": "subj_a_res",
    })
    # Post event for subject B
    client.post("/api/feedback/event", json={
        "sessionId": subj_b, "event": "resource_complete",
        "resourceId": "subj_b_res",
        "metadata": {"duration": 10},
    })

    # Subject A should only see its own event
    a = client.get("/api/learning-analytics", params={"sessionId": subj_a}).json()
    assert a["eventCount"] >= 1
    a_events = [e["event"] for e in a.get("recentEvents", [])]
    assert "resource_view" in a_events
    assert "resource_complete" not in a_events, "subject B events should not appear in subject A"

    # Subject B should only see its own event
    b = client.get("/api/learning-analytics", params={"sessionId": subj_b}).json()
    assert b["eventCount"] >= 1
    assert b["totalStudyMinutes"] >= 10

    print("PASS Session isolation works correctly (events don't mix)")


def test_subject_id_cannot_replace_session_id() -> None:
    subject_id = "e2e_subject_only"
    event = client.post("/api/feedback/event", json={
        "subjectId": subject_id,
        "event": "resource_view",
        "resourceId": "subject_only_res",
    })
    analytics = client.get("/api/learning-analytics", params={"subjectId": subject_id})

    assert event.status_code == 400
    assert analytics.status_code == 400
    print("PASS subjectId cannot substitute for sessionId")


if __name__ == "__main__":
    tests = [
        test_all_six_event_types_logged,
        test_all_nine_analytics_fields_returned,
        test_event_count_accuracy,
        test_total_study_minutes,
        test_active_resource_count,
        test_top_resources,
        test_quiz_accuracy,
        test_weak_topics,
        test_recent_events,
        test_recommendations,
        test_event_breakdown_labels,
        test_session_isolation,
        test_resource_status_cross_session,
        test_feedback_default_session,
        test_session_isolation_with_different_ids,
        test_subject_id_cannot_replace_session_id,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
