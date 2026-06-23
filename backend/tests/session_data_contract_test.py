import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.engine import SessionLocal
from app.db.models import SessionModel
from app.db.repository import (
    get_event_analytics,
    get_latest_learning_path,
    get_latest_profile,
    get_resources,
)
from app.main import app
from app.routers import product
from app.schemas.agent import AgentRunRequest
from app.services import agent_service
from app.services.conversation_state import conversation_store
from app.services.learning_tracker import LearningTracker
from app.services.llm_client import MockLLMClient
from app.services.orchestrator import AgentOrchestrator


client = TestClient(app)


class DeterministicTestOrchestrator(AgentOrchestrator):
    """Keep session-isolation tests independent from external LLM behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.llm_client = MockLLMClient()


def _run_agents(**kwargs):
    with patch.object(agent_service, "AgentOrchestrator", DeterministicTestOrchestrator):
        return agent_service.run_agents(**kwargs)

_EXPECTED_PROFILE_KEYS = {
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
}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _assert_profile_dimensions(profile, label: str) -> None:
    """Verify profile has all 10 expected dimensions with structured fields."""
    dims = profile.dimensions or []
    keys = {dim.get("key") for dim in dims}
    assert_true(keys == _EXPECTED_PROFILE_KEYS,
                f"{label} profile should store 10 dimensions, got {keys}")
    assert_true(
        all(all(f in dim for f in ("score", "confidence", "explanation", "evidence", "source"))
            for dim in dims),
        f"{label} profile dimensions should keep structured fields",
    )
    assert_true(
        all(dim.get("source") != "unknown" for dim in dims),
        f"{label} profile snapshots should not persist unknown sources",
    )


def _assert_session_path_scoped(path, session_id: str, label: str) -> None:
    """Verify learning path belongs to the correct session."""
    assert_true(path is not None, f"{label} should have a learning path")
    assert_true(path.session_id == session_id,
                f"{label} path belongs to session {session_id}, got {path.session_id}")
    assert_true(path.id.startswith(f"path_{session_id}_"),
                f"{label} path id should include session id, got {path.id}")


def _assert_resource_isolation(resources_a, resources_b, session_a: str, session_b: str) -> None:
    """Verify resources are scoped to their sessions and don't overlap."""
    ids_a = {r.id for r in resources_a}
    ids_b = {r.id for r in resources_b}
    assert_true(ids_a.isdisjoint(ids_b),
                f"resource IDs must not overlap across sessions {session_a} and {session_b}")
    assert_true(
        all(r.session_id == session_a and r.id.startswith(f"{session_a}_") for r in resources_a),
        f"all resources in session {session_a} must be scoped to it",
    )
    assert_true(
        all(r.session_id == session_b and r.id.startswith(f"{session_b}_") for r in resources_b),
        f"all resources in session {session_b} must be scoped to it",
    )


def _cleanup(session_ids: list[str]) -> None:
    for session_id in session_ids:
        conversation_store._sessions.pop(session_id, None)
    db = SessionLocal()
    try:
        for session_id in session_ids:
            session = db.get(SessionModel, session_id)
            if session:
                db.delete(session)
        db.commit()
    finally:
        db.close()


def test_generated_data_is_readable_by_session_and_isolated() -> None:
    session_a = "p0_session_a"
    session_b = "p0_session_b"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        _run_agents(
            session_id=session_a,
            course_id="data_structures",
            user_message="Data structures review: linked lists, stacks, queues, trees and sorting in 48 hours.",
        )
        _run_agents(
            session_id=session_b,
            course_id="ai_intro",
            user_message="Artificial intelligence introduction: machine learning, neural networks and NLP in 10 days.",
        )

        db = SessionLocal()
        try:
            profile_a = get_latest_profile(db, session_a)
            path_a = get_latest_learning_path(db, session_a)
            resources_a = get_resources(db, session_a)
            profile_b = get_latest_profile(db, session_b)
            path_b = get_latest_learning_path(db, session_b)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        assert_true(profile_a is not None, "session A should read generated profile")
        assert_true(path_a is not None, "session A should read generated learning path")
        assert_true(resources_a, "session A should read generated resources")
        assert_true(profile_b is not None, "session B should read generated profile")
        assert_true(path_b is not None, "session B should read generated learning path")
        assert_true(resources_b, "session B should read generated resources")
        expected_profile_keys = {
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
        }
        dims_a = profile_a.dimensions or []
        dims_b = profile_b.dimensions or []
        assert_true({dim.get("key") for dim in dims_a} == expected_profile_keys, "session A profile snapshot should store 10 dimensions")
        assert_true({dim.get("key") for dim in dims_b} == expected_profile_keys, "session B profile snapshot should store 10 dimensions")
        assert_true(
            all(all(field in dim for field in ("score", "confidence", "explanation", "evidence", "source")) for dim in dims_a),
            "session A profile snapshot should keep structured dimension fields",
        )
        assert_true(
            all(dim.get("source") != "unknown" for dim in dims_a + dims_b),
            "profile snapshots should not persist unknown sources",
        )

        assert_true(path_a.session_id == session_a, "session A path should belong to session A")
        assert_true(path_b.session_id == session_b, "session B path should belong to session B")
        assert_true(path_a.course_id == "data_structures", "session A should keep its data structures path")
        assert_true(path_b.course_id == "ai_intro", "session B should keep its AI path")
        assert_true(path_a.id != path_b.id, "path ids should be session scoped")
        assert_true(path_a.id.startswith(f"path_{session_a}_"), "session A path id should include session id")
        assert_true(path_b.id.startswith(f"path_{session_b}_"), "session B path id should include session id")

        ids_a = {resource.id for resource in resources_a}
        ids_b = {resource.id for resource in resources_b}
        assert_true(ids_a.isdisjoint(ids_b), "resource ids should not overlap across sessions")
        assert_true(
            all(resource.session_id == session_a and resource.id.startswith(f"{session_a}_") for resource in resources_a),
            "session A resources should be scoped to session A",
        )
        assert_true(
            all(resource.session_id == session_b and resource.id.startswith(f"{session_b}_") for resource in resources_b),
            "session B resources should be scoped to session B",
        )

        diagnosis_context = product._diagnosis_context("\u6211\u54ea\u91cc\u6bd4\u8f83\u8584\u5f31", session_a)
        assert_true(
            all(
                str(item.get("resource_id") or item.get("id") or "").startswith(f"{session_a}_")
                for item in diagnosis_context["resources"]
            ),
            "session A diagnosis context must only contain session A resources",
        )
        diagnosis = product._run_diagnosis("\u6211\u54ea\u91cc\u6bd4\u8f83\u8584\u5f31", session_a)
        recommended_ids = diagnosis.get("recommended_resource_ids") or []
        assert_true(
            all(str(resource_id).startswith(f"{session_a}_") for resource_id in recommended_ids),
            "session A diagnosis must not recommend resources from session B",
        )
    finally:
        _cleanup(sessions)


# ── Scenario 1: Same subject, different sessions ──────────────────────

def test_same_subject_different_sessions_isolation() -> None:
    """Same course (ai_intro), two different sessions — data must not leak."""
    session_a = "contract_same_subj_a"
    session_b = "contract_same_subj_b"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        _run_agents(
            session_id=session_a, course_id="ai_intro",
            user_message="我是大一学生，想入门人工智能",
        )
        _run_agents(
            session_id=session_b, course_id="ai_intro",
            user_message="我是大一学生，想入门人工智能",
        )

        db = SessionLocal()
        try:
            profile_a = get_latest_profile(db, session_a)
            profile_b = get_latest_profile(db, session_b)
            path_a = get_latest_learning_path(db, session_a)
            path_b = get_latest_learning_path(db, session_b)
            resources_a = get_resources(db, session_a)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        _assert_profile_dimensions(profile_a, "session A")
        _assert_profile_dimensions(profile_b, "session B")
        _assert_session_path_scoped(path_a, session_a, "session A")
        _assert_session_path_scoped(path_b, session_b, "session B")
        assert_true(path_a.id != path_b.id, "path IDs must differ between sessions")
        _assert_resource_isolation(resources_a, resources_b, session_a, session_b)
    finally:
        _cleanup(sessions)


# ── Scenario 2: Different subjects, different sessions ────────────────

def test_different_subjects_different_sessions_isolation() -> None:
    """Different courses, different sessions — data must not leak."""
    session_a = "contract_diff_subj_a"
    session_b = "contract_diff_subj_b"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        _run_agents(
            session_id=session_a, course_id="ai_intro",
            user_message="我是大一学生，想入门人工智能",
        )
        _run_agents(
            session_id=session_b, course_id="data_structures",
            user_message="我是软件工程大一学生，想复习数据结构",
        )

        db = SessionLocal()
        try:
            profile_a = get_latest_profile(db, session_a)
            profile_b = get_latest_profile(db, session_b)
            path_a = get_latest_learning_path(db, session_a)
            path_b = get_latest_learning_path(db, session_b)
            resources_a = get_resources(db, session_a)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        _assert_profile_dimensions(profile_a, "session A (ai_intro)")
        _assert_profile_dimensions(profile_b, "session B (data_structures)")
        _assert_session_path_scoped(path_a, session_a, "session A")
        _assert_session_path_scoped(path_b, session_b, "session B")
        _assert_resource_isolation(resources_a, resources_b, session_a, session_b)
    finally:
        _cleanup(sessions)


# ── Scenario 3: Order variation — AI Intro first, Data Structures second

def test_order_variation_ai_intro_then_ds() -> None:
    """Generate AI Intro first, then Data Structures — no cross-contamination."""
    session_a = "contract_order_ai_first"
    session_b = "contract_order_ds_second"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        _run_agents(
            session_id=session_a, course_id="ai_intro",
            user_message="我是大一学生，想入门人工智能",
        )
        _run_agents(
            session_id=session_b, course_id="data_structures",
            user_message="我是软件工程大一学生，想复习数据结构",
        )

        db = SessionLocal()
        try:
            path_a = get_latest_learning_path(db, session_a)
            path_b = get_latest_learning_path(db, session_b)
            resources_a = get_resources(db, session_a)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        _assert_session_path_scoped(path_a, session_a, "session A (AI first)")
        _assert_session_path_scoped(path_b, session_b, "session B (DS second)")
        _assert_resource_isolation(resources_a, resources_b, session_a, session_b)
    finally:
        _cleanup(sessions)


# ── Scenario 4: Order variation — Data Structures first, AI Intro second

def test_order_variation_ds_then_ai_intro() -> None:
    """Generate Data Structures first, then AI Intro — no cross-contamination."""
    session_a = "contract_order_ds_first"
    session_b = "contract_order_ai_second"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        _run_agents(
            session_id=session_a, course_id="data_structures",
            user_message="我是软件工程大一学生，想复习数据结构",
        )
        _run_agents(
            session_id=session_b, course_id="ai_intro",
            user_message="我是大一学生，想入门人工智能",
        )

        db = SessionLocal()
        try:
            path_a = get_latest_learning_path(db, session_a)
            path_b = get_latest_learning_path(db, session_b)
            resources_a = get_resources(db, session_a)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        _assert_session_path_scoped(path_a, session_a, "session A (DS first)")
        _assert_session_path_scoped(path_b, session_b, "session B (AI second)")
        _assert_resource_isolation(resources_a, resources_b, session_a, session_b)
    finally:
        _cleanup(sessions)


# ── Scenario 5: Learning analytics session isolation ──────────────────

def test_learning_analytics_session_isolation() -> None:
    """Learning analytics must be isolated per session."""
    session_a = "contract_analytics_a"
    session_b = "contract_analytics_b"
    sessions = [session_a, session_b]
    conversation_store.enable_db()
    _cleanup(sessions)

    try:
        for session_id in sessions:
            _run_agents(
                session_id=session_id, course_id="ai_intro",
                user_message="学习人工智能",
            )

        db = SessionLocal()
        try:
            analytics_a = get_event_analytics(db, session_a)
            analytics_b = get_event_analytics(db, session_b)
        finally:
            db.close()

        assert_true(isinstance(analytics_a, dict), "session A should return analytics dict")
        assert_true(isinstance(analytics_b, dict), "session B should return analytics dict")
        assert_true(analytics_a.get("eventCount", -1) >= 0, "session A analytics has eventCount")
        assert_true(analytics_b.get("eventCount", -1) >= 0, "session B analytics has eventCount")
    finally:
        _cleanup(sessions)


# ── Scenario 6: Empty sessionId rejected at API level ─────────────────

def test_empty_session_id_rejected_at_api_level() -> None:
    """API endpoints must reject requests with missing sessionId."""
    # GET endpoints — no sessionId
    r = client.get("/api/profile")
    assert_true(r.status_code == 400, "profile without sessionId should return 400")
    assert_true("sessionId is required" in r.json().get("detail", ""),
                "error message must mention sessionId")

    r = client.get("/api/learning-path")
    assert_true(r.status_code == 400, "learning-path without sessionId should return 400")

    r = client.get("/api/resources")
    assert_true(r.status_code == 400, "resources without sessionId should return 400")

    r = client.get("/api/learning-analytics")
    assert_true(r.status_code == 400, "learning-analytics without sessionId should return 400")

    # POST endpoints — no sessionId in payload
    r = client.post("/api/chat/send", json={"message": "hello"})
    assert_true(r.status_code == 400, "chat/send without sessionId should return 400")

    r = client.post("/api/profile/build", json={"message": "hello"})
    assert_true(r.status_code == 400, "profile/build without sessionId should return 400")


def test_subject_id_never_substitutes_for_session_id() -> None:
    subject_id = "subject_only_must_not_be_session"
    conversation_store._sessions.pop(subject_id, None)

    profile_response = client.get("/api/profile", params={"subjectId": subject_id})
    path_response = client.get("/api/learning-path", params={"subjectId": subject_id})
    resources_response = client.get("/api/resources", params={"subjectId": subject_id})
    analytics_response = client.get("/api/learning-analytics", params={"subjectId": subject_id})
    event_response = client.post(
        "/api/feedback/event",
        json={"subjectId": subject_id, "event": "resource_view", "resourceId": "subject_only_resource"},
    )

    assert_true(profile_response.status_code == 400, "subjectId-only profile reads must be rejected")
    assert_true(path_response.status_code == 400, "subjectId-only path reads must be rejected")
    assert_true(resources_response.status_code == 400, "subjectId-only resource reads must be rejected")
    assert_true(analytics_response.status_code == 400, "subjectId-only analytics reads must be rejected")
    assert_true(event_response.status_code == 400, "subjectId-only event writes must be rejected")
    assert_true(
        conversation_store.get_state_or_none(subject_id) is None,
        "subjectId-only requests must not create a conversation session",
    )


def test_missing_session_id_is_rejected_without_default_writes() -> None:
    chat_response = client.post("/api/chat/send", json={"message": "hello"})
    profile_response = client.get("/api/profile")
    path_response = client.get("/api/learning-path")
    resources_response = client.get("/api/resources")
    event_response = client.post(
        "/api/feedback/event",
        json={"event": "resource_view", "resourceId": "missing_session_resource"},
    )
    agent_response = client.post(
        "/api/agents/run",
        json={"course_id": "data_structures", "user_message": "review stacks"},
    )

    assert_true(chat_response.status_code == 400, "chat must require sessionId")
    assert_true(profile_response.status_code == 400, "profile reads must require sessionId")
    assert_true(path_response.status_code == 400, "learning path reads must require sessionId")
    assert_true(resources_response.status_code == 400, "resource reads must require sessionId")
    assert_true(event_response.status_code == 400, "learning events must require sessionId")
    assert_true(agent_response.status_code == 422, "agent runs must require session_id")

    tracker = LearningTracker()
    try:
        tracker.log({"event": "resource_view", "resourceId": "missing_session_resource"})
    except ValueError as exc:
        assert_true("session_id is required" in str(exc), "tracker should explain the missing session")
    else:
        raise AssertionError("tracker must not log an event without a session")

    assert_true(
        AgentRunRequest(sessionId="agent_contract_camel").session_id == "agent_contract_camel",
        "agent requests should accept the sessionId API field",
    )
    assert_true(
        AgentRunRequest(session_id="agent_contract_snake").session_id == "agent_contract_snake",
        "agent requests should preserve the legacy session_id field name",
    )


if __name__ == "__main__":
    test_generated_data_is_readable_by_session_and_isolated()
    test_same_subject_different_sessions_isolation()
    test_different_subjects_different_sessions_isolation()
    test_order_variation_ai_intro_then_ds()
    test_order_variation_ds_then_ai_intro()
    test_learning_analytics_session_isolation()
    test_empty_session_id_rejected_at_api_level()
    test_subject_id_never_substitutes_for_session_id()
    test_missing_session_id_is_rejected_without_default_writes()
    print("PASS session_data_contract_test")
