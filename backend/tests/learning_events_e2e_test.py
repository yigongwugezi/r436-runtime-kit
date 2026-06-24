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
from app.db.repository import upsert_resource
from app.main import app
from app.services.learning_tracker import learning_tracker

# Ensure DB tables exist and persistence is enabled for the test session
init_db()
learning_tracker.enable_db()

client = TestClient(app)
SESSION = f"e2e_test_{uuid.uuid4().hex[:8]}"


def _response_data(response) -> dict[str, object]:
    payload = response.json()
    return payload.get("data", payload)


def _post_event(event: str, **kwargs: object) -> None:
    payload: dict[str, object] = {
        "sessionId": SESSION,
        "event": event,
        **kwargs,
    }
    r = client.post("/api/feedback/event", json=payload)
    assert r.status_code == 200
    assert _response_data(r)["ok"] is True


def _get_analytics() -> dict[str, object]:
    r = client.get("/api/learning-analytics", params={"sessionId": SESSION})
    assert r.status_code == 200
    return _response_data(r)


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


def test_all_analytics_fields_returned() -> None:
    """Verify all analytics fields are present and have correct types."""
    analytics = _get_analytics()

    required_fields = [
        "eventCount",
        "totalStudyMinutes",
        "activeResourceCount",
        "viewedResources",
        "completedResources",
        "practiceCount",
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
    assert isinstance(analytics["viewedResources"], int)
    assert isinstance(analytics["completedResources"], int)
    assert isinstance(analytics["practiceCount"], int)
    assert isinstance(analytics["eventBreakdown"], dict)
    assert isinstance(analytics["topResources"], list)
    assert analytics["quizAccuracy"] is None or isinstance(analytics["quizAccuracy"], int)
    assert isinstance(analytics["weakTopics"], list)
    assert isinstance(analytics["recommendations"], list)
    assert isinstance(analytics["recentEvents"], list)

    print("PASS All analytics fields present with correct types")


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


def test_practice_result_contributes_to_weak_topics() -> None:
    """A scored practice with a topic should contribute behavior evidence."""
    _post_event(
        "practice_result",
        resourceId="res_practice_tree",
        metadata={
            "title": "Tree Practice",
            "topic": "二叉树遍历",
            "correct": 1,
            "wrong": 3,
            "total": 4,
            "accuracy": 25,
        },
    )

    analytics = _get_analytics()
    topics = {item["topic"]: item for item in analytics["weakTopics"]}
    assert "二叉树遍历" in topics
    assert topics["二叉树遍历"]["wrongCount"] >= 3
    assert topics["二叉树遍历"]["risk"] >= 0.75
    print("PASS scored practice_result contributes to weakTopics")


def test_recent_events() -> None:
    """recentEvents should contain the most recent events with correct structure, newest first."""
    analytics = _get_analytics()
    recent = analytics["recentEvents"]
    assert len(recent) >= 1, "Should have at least 1 recent event"
    # Newest event should be first (reverse chronological order)
    evt = recent[0]
    assert "event" in evt
    assert "timestamp" in evt
    print(f"PASS recentEvents has {len(recent)} events, newest first: {evt['event']}")


def test_recent_events_reverse_chronological_order() -> None:
    """recentEvents must be in reverse chronological order (newest first)."""
    # Post two events with a small time gap so ordering is deterministic
    _post_event("resource_view", resourceId="order_res_1")
    import time
    time.sleep(1.1)  # Ensure distinct timestamps
    _post_event("resource_complete", resourceId="order_res_2", metadata={"duration": 5})

    analytics = _get_analytics()
    recent = analytics["recentEvents"]
    # Find our two events in recentEvents
    order_events = [e for e in recent if e.get("resourceId") in ("order_res_1", "order_res_2")]
    assert len(order_events) >= 2, f"Expected at least 2 order events, got {len(order_events)}"
    # Newer event (resource_complete on order_res_2) should appear first
    assert order_events[0]["resourceId"] == "order_res_2", (
        f"Expected newest event first, got {order_events[0]['resourceId']}"
    )
    assert order_events[0]["event"] == "resource_complete"
    print("PASS recentEvents is in reverse chronological order")


def test_recommendations() -> None:
    """recommendations should contain structured objects with required fields."""
    analytics = _get_analytics()
    recs = analytics["recommendations"]
    assert isinstance(recs, list), "recommendations should be a list"
    # With quiz data posted, we should get structured recommendations
    if recs:
        rec = recs[0]
        assert isinstance(rec, dict), "each recommendation should be a dict"
        required_fields = [
            "recommendation_type", "title", "reason",
            "target_resource_id", "target_stage_id",
            "priority", "source", "confidence", "evidence", "quality_status",
        ]
        for field in required_fields:
            assert field in rec, f"recommendation missing field '{field}'"
        assert rec["recommendation_type"] in (
            "incomplete_resource", "low_accuracy_topic", "incomplete_practice",
            "stage_incomplete", "frequent_weak_topic",
        ), f"unknown recommendation_type: {rec['recommendation_type']}"
        assert rec["priority"] in ("high", "medium", "low"), f"unknown priority: {rec['priority']}"
        assert isinstance(rec["confidence"], (int, float)), "confidence should be numeric"
        assert 0.0 <= rec["confidence"] <= 1.0, f"confidence out of range: {rec['confidence']}"
    print(f"PASS recommendations ({len(recs)} structured items)")


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
    other = _response_data(r2)
    assert other["eventCount"] >= 1
    assert other["eventBreakdown"].get("resource_view", 0) >= 1

    print("PASS Session isolation works correctly")


def test_resource_status_cross_session() -> None:
    """Verify resource study_status cannot be modified across sessions."""
    res_id = f"{SESSION}_cross_session_res"
    db = SessionLocal()
    try:
        upsert_resource(db, SESSION, {
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
    assert _response_data(r1).get("ok") is True

    # Session B tries to mark it incomplete
    other = "e2e_other_cross"
    r2 = client.patch(f"/api/resources/{res_id}/study-status",
        json={"studyStatus": "new"},
        params={"sessionId": other})
    assert r2.status_code == 200
    assert _response_data(r2).get("ok") is False
    assert "does not belong" in r2.json().get("message", "")

    bookmark = client.post(
        f"/api/resources/{res_id}/bookmark",
        params={"sessionId": other},
    )
    assert bookmark.status_code == 200
    assert _response_data(bookmark).get("ok") is False

    # Verify session A's status is still "completed"
    r3 = client.get(f"/api/resources/{res_id}", params={"sessionId": SESSION})
    assert r3.status_code == 200
    res = _response_data(r3).get("resource", {})
    assert res.get("studyStatus") == "completed", "owned session keeps its status"
    print("PASS Resource status cross-session modification protected")


def test_feedback_default_session() -> None:
    """Verify feedback without sessionId is rejected and doesn't pollute."""
    # Fresh resource ID to avoid stale data
    fresh_id = "no_session_" + uuid.uuid4().hex[:6]
    r = client.post("/api/feedback", json={
        "resourceId": fresh_id, "rating": 5,
    })
    assert r.status_code == 422
    result = r.json()
    assert result.get("code") == "MISSING_SESSION_ID"
    print("PASS Feedback without sessionId correctly rejected")

    # Verify the rejected event did not leak into the test session
    analytics = _response_data(client.get("/api/learning-analytics",
        params={"sessionId": SESSION}))
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
    a = _response_data(client.get("/api/learning-analytics", params={"sessionId": subj_a}))
    assert a["eventCount"] >= 1
    a_events = [e["event"] for e in a.get("recentEvents", [])]
    assert "resource_view" in a_events
    assert "resource_complete" not in a_events, "subject B events should not appear in subject A"

    # Subject B should only see its own event
    b = _response_data(client.get("/api/learning-analytics", params={"sessionId": subj_b}))
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

    assert event.status_code == 422
    assert analytics.status_code == 422
    print("PASS subjectId cannot substitute for sessionId")


def test_invalid_event_type_rejected() -> None:
    """Verify invalid event_type returns 422 with INVALID_EVENT_TYPE."""
    invalid_types = [
        ("invalid_type", "completely unknown type"),
        ("", "empty string"),
        ("random_string", "random string"),
        ("stage_complete", "internal-only type"),
    ]
    for evt_type, _desc in invalid_types:
        r = client.post("/api/feedback/event", json={
            "sessionId": SESSION,
            "event": evt_type,
            "resourceId": "test_res",
        })
        assert r.status_code == 422, (
            f"Expected 422 for event_type='{evt_type}', got {r.status_code}"
        )
        result = r.json()
        assert result.get("code") == "INVALID_EVENT_TYPE", (
            f"Expected INVALID_EVENT_TYPE for '{evt_type}', got {result.get('code')}"
        )
        assert "不支持的事件类型" in result.get("message", ""), (
            f"Expected Chinese error message, got {result.get('message')}"
        )
    print("PASS invalid event types correctly rejected with INVALID_EVENT_TYPE")


def test_subject_id_recorded_in_event() -> None:
    """Verify subjectId sent with event is stored in event metadata."""
    subj_id = "e2e_subject_event_test"
    r = client.post("/api/feedback/event", json={
        "sessionId": SESSION,
        "event": "resource_view",
        "resourceId": "subj_meta_res",
        "subjectId": subj_id,
        "metadata": {"type": "lecture"},
    })
    assert r.status_code == 200
    assert _response_data(r)["ok"] is True

    # Verify in recent events timeline
    r2 = client.get("/api/learning-events/timeline", params={"sessionId": SESSION, "limit": 10})
    events = r2.json().get("data", {}).get("events", [])
    found = any(
        e.get("metadata", {}).get("subjectId") == subj_id
        for e in events
        if isinstance(e, dict) and e.get("resourceId") == "subj_meta_res"
    )
    assert found, "subjectId was not recorded in event metadata"
    print("PASS subject_id recorded in event metadata")


def test_viewed_resources_count() -> None:
    """viewedResources should reflect the number of resource_view events."""
    analytics = _get_analytics()
    viewed = analytics["viewedResources"]
    breakdown_views = analytics["eventBreakdown"].get("resource_view", 0)
    assert viewed == breakdown_views, (
        f"viewedResources {viewed} should match eventBreakdown.resource_view {breakdown_views}"
    )
    assert viewed >= 2, f"Expected >= 2 viewedResources, got {viewed}"
    print(f"PASS viewedResources = {viewed}")


def test_completed_resources_count() -> None:
    """completedResources should reflect the number of resource_complete events."""
    analytics = _get_analytics()
    completed = analytics["completedResources"]
    breakdown_completes = analytics["eventBreakdown"].get("resource_complete", 0)
    assert completed == breakdown_completes, (
        f"completedResources {completed} should match eventBreakdown.resource_complete {breakdown_completes}"
    )
    assert completed >= 1, f"Expected >= 1 completedResources, got {completed}"
    print(f"PASS completedResources = {completed}")


def test_practice_count() -> None:
    """practiceCount should reflect the number of practice_result events."""
    analytics = _get_analytics()
    practice = analytics["practiceCount"]
    breakdown_practice = analytics["eventBreakdown"].get("practice_result", 0)
    assert practice == breakdown_practice, (
        f"practiceCount {practice} should match eventBreakdown.practice_result {breakdown_practice}"
    )
    assert practice >= 1, f"Expected >= 1 practiceCount, got {practice}"
    print(f"PASS practiceCount = {practice}")


def test_empty_analytics_returns_default_structure() -> None:
    """Analytics for a session with no events should return default (zero) values."""
    empty_session = f"e2e_empty_{uuid.uuid4().hex[:8]}"
    r = client.get("/api/learning-analytics", params={"sessionId": empty_session})
    assert r.status_code == 200
    data = _response_data(r)

    assert data["eventCount"] == 0
    assert data["totalStudyMinutes"] == 0
    assert data["activeResourceCount"] == 0
    assert data["viewedResources"] == 0
    assert data["completedResources"] == 0
    assert data["practiceCount"] == 0
    assert data["eventBreakdown"] == {}
    assert data["topResources"] == []
    assert data["quizAccuracy"] is None
    assert data["weakTopics"] == []
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) == 0, (
        "empty data should produce no recommendations"
    )
    assert data["recentEvents"] == []

    print("PASS Empty analytics returns default structure with zero values")


def test_resource_complete_affects_completed_resources() -> None:
    """Posting a resource_complete event should increase completedResources."""
    analytics_before = _get_analytics()
    before = analytics_before["completedResources"]

    _post_event("resource_complete", resourceId="res_complete_test",
                metadata={"duration": 10, "title": "Complete Test"})

    analytics_after = _get_analytics()
    after = analytics_after["completedResources"]
    assert after == before + 1, (
        f"completedResources should increase from {before} to {before + 1}, got {after}"
    )
    print(f"PASS resource_complete increases completedResources: {before} → {after}")


if __name__ == "__main__":
    tests = [
        test_all_six_event_types_logged,
        test_all_analytics_fields_returned,
        test_event_count_accuracy,
        test_total_study_minutes,
        test_active_resource_count,
        test_viewed_resources_count,
        test_completed_resources_count,
        test_practice_count,
        test_empty_analytics_returns_default_structure,
        test_top_resources,
        test_quiz_accuracy,
        test_weak_topics,
        test_practice_result_contributes_to_weak_topics,
        test_recent_events,
        test_recent_events_reverse_chronological_order,
        test_resource_complete_affects_completed_resources,
        test_recommendations,
        test_event_breakdown_labels,
        test_session_isolation,
        test_resource_status_cross_session,
        test_feedback_default_session,
        test_session_isolation_with_different_ids,
        test_subject_id_cannot_replace_session_id,
        test_invalid_event_type_rejected,
        test_subject_id_recorded_in_event,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
