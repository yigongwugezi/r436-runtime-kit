"""Session data contract regression tests.

Validates that:
- Different sessions / subjects do not mix data.
- sessionId is the sole data ownership key.
- subjectId is course context only, NOT a session identifier.
- No hardcoded ``frontend_session_001`` fallback exists.
- Empty sessionId is rejected (422).

Usage::

    cd backend
    python -m pytest tests/session_data_contract_test.py -v
"""

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db import init_db
from app.db.engine import SessionLocal
from app.db.models import SessionModel
from app.db.repository import get_latest_learning_path, get_latest_profile, get_resources
from app.main import app
from app.services import agent_service
from app.services.conversation_state import conversation_store

init_db()
conversation_store.enable_db()

client = TestClient(app)


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


# ═══════════════════════════════════════════════════════════════════════
# Original contract test (preserved)
# ═══════════════════════════════════════════════════════════════════════


def test_generated_data_is_readable_by_session_and_isolated() -> None:
    """Two sessions with same course — data must be isolated."""
    session_a = "p0_session_a"
    session_b = "p0_session_b"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        for session_id in sessions:
            agent_service.run_agents(
                session_id=session_id,
                course_id="data_structures",
                user_message="我是软件工程大二学生，想48小时复习数据结构，为了考试通过，喜欢图解和练习题",
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

        assert profile_a is not None, "session A should read generated profile"
        assert path_a is not None, "session A should read generated learning path"
        assert resources_a, "session A should read generated resources"
        assert profile_b is not None, "session B should read generated profile"
        assert path_b is not None, "session B should read generated learning path"
        assert resources_b, "session B should read generated resources"

        expected_profile_keys = {
            "major_background", "knowledge_base", "learning_goal",
            "cognitive_style", "error_patterns", "coding_ability",
            "learning_progress", "interest_direction", "learning_rhythm",
            "self_efficacy",
        }
        dims_a = profile_a.dimensions or []
        dims_b = profile_b.dimensions or []
        assert {dim.get("key") for dim in dims_a} == expected_profile_keys, \
            "session A profile snapshot should store 10 dimensions"
        assert {dim.get("key") for dim in dims_b} == expected_profile_keys, \
            "session B profile snapshot should store 10 dimensions"
        assert all(
            all(field in dim for field in ("score", "confidence", "explanation", "evidence", "source"))
            for dim in dims_a
        ), "session A profile snapshot should keep structured dimension fields"
        assert all(
            dim.get("source") != "unknown" for dim in dims_a + dims_b
        ), "profile snapshots should not persist unknown sources"

        assert path_a.session_id == session_a, "session A path should belong to session A"
        assert path_b.session_id == session_b, "session B path should belong to session B"
        assert path_a.id != path_b.id, "path ids should be session scoped"
        assert path_a.id.startswith(f"path_{session_a}_"), \
            "session A path id should include session id"
        assert path_b.id.startswith(f"path_{session_b}_"), \
            "session B path id should include session id"

        ids_a = {resource.id for resource in resources_a}
        ids_b = {resource.id for resource in resources_b}
        assert ids_a.isdisjoint(ids_b), "resource ids should not overlap across sessions"
        assert all(
            resource.session_id == session_a and resource.id.startswith(f"{session_a}_")
            for resource in resources_a
        ), "session A resources should be scoped to session A"
        assert all(
            resource.session_id == session_b and resource.id.startswith(f"{session_b}_")
            for resource in resources_b
        ), "session B resources should be scoped to session B"
    finally:
        _cleanup(sessions)


# ═══════════════════════════════════════════════════════════════════════
# Scenario 1: Same subject, different sessions — data isolated
# ═══════════════════════════════════════════════════════════════════════


def test_same_subject_different_sessions() -> None:
    """Same course (subject), different sessionIds — data must be isolated."""
    session_a = "same_subj_sess_a"
    session_b = "same_subj_sess_b"
    sessions = [session_a, session_b]
    _cleanup(sessions)
    common_course = "data_structures"

    try:
        for session_id in sessions:
            agent_service.run_agents(
                session_id=session_id,
                course_id=common_course,
                user_message="我是软件工程大二学生，想48小时复习数据结构，为了考试通过，喜欢图解和练习题",
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

        assert profile_a is not None, "session A should have profile"
        assert profile_b is not None, "session B should have profile"
        assert path_a.session_id == session_a
        assert path_b.session_id == session_b
        assert path_a.id != path_b.id, "paths should have different IDs"

        # Resource ids must be disjoint
        ids_a = {r.id for r in resources_a}
        ids_b = {r.id for r in resources_b}
        assert ids_a.isdisjoint(ids_b), \
            "same subject, different sessions: resource IDs must not overlap"
    finally:
        _cleanup(sessions)


# ═══════════════════════════════════════════════════════════════════════
# Scenario 2: Different subjects, different sessions — data isolated
# ═══════════════════════════════════════════════════════════════════════


def test_different_subjects_different_sessions() -> None:
    """Session A with AI Intro, Session B with Data Structures — no cross-contamination."""
    session_a = "diff_subj_sess_a"
    session_b = "diff_subj_sess_b"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        agent_service.run_agents(
            session_id=session_a,
            course_id="ai_intro",
            user_message="我是计算机专业学生，想学人工智能导论，零基础",
        )
        agent_service.run_agents(
            session_id=session_b,
            course_id="data_structures",
            user_message="我是软件工程学生，要复习数据结构准备考试",
        )

        db = SessionLocal()
        try:
            profile_a = get_latest_profile(db, session_a)
            path_a = get_latest_learning_path(db, session_a)
            profile_b = get_latest_profile(db, session_b)
            path_b = get_latest_learning_path(db, session_b)
        finally:
            db.close()

        assert profile_a is not None
        assert profile_b is not None
        assert path_a is not None
        assert path_b is not None

        # Each session's path should reference its own course
        assert path_a.course_id == "ai_intro", \
            f"Session A should have ai_intro course, got {path_a.course_id}"
        assert path_b.course_id == "data_structures", \
            f"Session B should have data_structures course, got {path_b.course_id}"

        # Path IDs must differ
        assert path_a.id != path_b.id
        assert path_a.session_id == session_a
        assert path_b.session_id == session_b
    finally:
        _cleanup(sessions)


# ═══════════════════════════════════════════════════════════════════════
# Scenario 3 & 4: Cross-course ordering — no contamination in either direction
# ═══════════════════════════════════════════════════════════════════════


def test_cross_course_ai_first_then_ds() -> None:
    """Generate AI Intro first, then Data Structures — no cross-contamination."""
    session_a = "cross_ai_then_ds_a"
    session_b = "cross_ai_then_ds_b"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        # Session A: generate AI Intro
        agent_service.run_agents(
            session_id=session_a,
            course_id="ai_intro",
            user_message="我想学人工智能导论，零基础",
        )
        # Session B: generate Data Structures
        agent_service.run_agents(
            session_id=session_b,
            course_id="data_structures",
            user_message="我要复习数据结构准备考试",
        )

        db = SessionLocal()
        try:
            path_a = get_latest_learning_path(db, session_a)
            path_b = get_latest_learning_path(db, session_b)
            resources_a = get_resources(db, session_a)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        assert path_a is not None, "session A should have path"
        assert path_b is not None, "session B should have path"
        assert path_a.course_id == "ai_intro", \
            f"Session A should be ai_intro, got {path_a.course_id}"
        assert path_b.course_id == "data_structures", \
            f"Session B should be data_structures, got {path_b.course_id}"

        # Resource IDs must not overlap
        ids_a = {r.id for r in resources_a}
        ids_b = {r.id for r in resources_b}
        assert ids_a.isdisjoint(ids_b), \
            "AI first: resource IDs between ai_intro and data_structures sessions must not overlap"
    finally:
        _cleanup(sessions)


def test_cross_course_ds_first_then_ai() -> None:
    """Generate Data Structures first, then AI Intro — no cross-contamination."""
    session_a = "cross_ds_then_ai_a"
    session_b = "cross_ds_then_ai_b"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        # Session A: generate Data Structures
        agent_service.run_agents(
            session_id=session_a,
            course_id="data_structures",
            user_message="我要复习数据结构准备考试",
        )
        # Session B: generate AI Intro
        agent_service.run_agents(
            session_id=session_b,
            course_id="ai_intro",
            user_message="我想学人工智能导论，零基础",
        )

        db = SessionLocal()
        try:
            path_a = get_latest_learning_path(db, session_a)
            path_b = get_latest_learning_path(db, session_b)
            resources_a = get_resources(db, session_a)
            resources_b = get_resources(db, session_b)
        finally:
            db.close()

        assert path_a is not None
        assert path_b is not None
        assert path_a.course_id == "data_structures", \
            f"Session A should be data_structures, got {path_a.course_id}"
        assert path_b.course_id == "ai_intro", \
            f"Session B should be ai_intro, got {path_b.course_id}"

        ids_a = {r.id for r in resources_a}
        ids_b = {r.id for r in resources_b}
        assert ids_a.isdisjoint(ids_b), \
            "DS first: resource IDs between data_structures and ai_intro sessions must not overlap"
    finally:
        _cleanup(sessions)


# ═══════════════════════════════════════════════════════════════════════
# Scenario 5-8: Profile / Path / Resources / Analytics API-level isolation
# ═══════════════════════════════════════════════════════════════════════


def test_profile_isolation_via_api() -> None:
    """GET /profile?sessionId=A returns only session A data."""
    session_a = f"api_profile_a_{uuid.uuid4().hex[:6]}"
    session_b = f"api_profile_b_{uuid.uuid4().hex[:6]}"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        for sid in sessions:
            agent_service.run_agents(
                session_id=sid,
                course_id="data_structures",
                user_message="我是软件工程大二学生，想学数据结构",
            )

        r_a = client.get("/api/profile", params={"sessionId": session_a})
        assert r_a.status_code == 200, f"profile A: expected 200 got {r_a.status_code}"
        profile_a = r_a.json()["data"].get("profile", {})
        assert profile_a.get("id") == session_a, \
            f"profile id should match session A ({session_a}), got {profile_a.get('id')}"

        r_b = client.get("/api/profile", params={"sessionId": session_b})
        assert r_b.status_code == 200
        profile_b = r_b.json()["data"].get("profile", {})
        assert profile_b.get("id") == session_b

        assert profile_a.get("id") != profile_b.get("id"), \
            "profile IDs must differ across sessions"
    finally:
        _cleanup(sessions)


def test_path_isolation_via_api() -> None:
    """GET /learning-path?sessionId=A returns only session A path."""
    session_a = f"api_path_a_{uuid.uuid4().hex[:6]}"
    session_b = f"api_path_b_{uuid.uuid4().hex[:6]}"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        for sid in sessions:
            agent_service.run_agents(
                session_id=sid,
                course_id="data_structures",
                user_message="我是大二学生，想学数据结构",
            )

        r_a = client.get("/api/learning-path", params={"sessionId": session_a})
        assert r_a.status_code == 200
        data_a = r_a.json()["data"]
        path_id_a = data_a.get("id") or data_a.get("path", {}).get("id", "")
        assert path_id_a, f"path A should have an id, got {list(data_a.keys())}"
        assert path_id_a.startswith(f"path_{session_a}_"), \
            f"path A id should start with path_{session_a}_, got {path_id_a}"

        r_b = client.get("/api/learning-path", params={"sessionId": session_b})
        assert r_b.status_code == 200
        data_b = r_b.json()["data"]
        path_id_b = data_b.get("id") or data_b.get("path", {}).get("id", "")
        assert path_id_b.startswith(f"path_{session_b}_"), \
            f"path B id should start with path_{session_b}_, got {path_id_b}"
    finally:
        _cleanup(sessions)


def test_resources_isolation_via_api() -> None:
    """GET /resources?sessionId=A returns only session A resources."""
    session_a = f"api_res_a_{uuid.uuid4().hex[:6]}"
    session_b = f"api_res_b_{uuid.uuid4().hex[:6]}"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        for sid in sessions:
            agent_service.run_agents(
                session_id=sid,
                course_id="data_structures",
                user_message="我是大二学生，想学数据结构",
            )

        r_a = client.get("/api/resources", params={"sessionId": session_a})
        assert r_a.status_code == 200
        resources_a = r_a.json()["data"].get("resources", [])

        r_b = client.get("/api/resources", params={"sessionId": session_b})
        assert r_b.status_code == 200
        resources_b = r_b.json()["data"].get("resources", [])

        ids_a = {r.get("id", "") for r in resources_a if r.get("id")}
        ids_b = {r.get("id", "") for r in resources_b if r.get("id")}

        assert ids_a.isdisjoint(ids_b), \
            f"resource IDs must not overlap between sessions ({len(ids_a)} vs {len(ids_b)})"

        for r in resources_a:
            rid = r.get("id", "")
            assert rid.startswith(f"{session_a}_"), \
                f"resource {rid} should be prefixed with {session_a}_"
    finally:
        _cleanup(sessions)


def test_analytics_isolation_via_api() -> None:
    """GET /learning-analytics?sessionId=A returns only session A analytics."""
    session_a = f"api_analytics_a_{uuid.uuid4().hex[:6]}"
    session_b = f"api_analytics_b_{uuid.uuid4().hex[:6]}"
    sessions = [session_a, session_b]
    _cleanup(sessions)

    try:
        for sid in sessions:
            agent_service.run_agents(
                session_id=sid,
                course_id="data_structures",
                user_message="我是大二学生，想学数据结构",
            )

        r_a = client.get("/api/learning-analytics", params={"sessionId": session_a})
        assert r_a.status_code == 200
        analytics_a = r_a.json()["data"]
        assert "eventCount" in analytics_a, f"analytics A should have eventCount"

        r_b = client.get("/api/learning-analytics", params={"sessionId": session_b})
        assert r_b.status_code == 200
        analytics_b = r_b.json()["data"]
        assert "eventCount" in analytics_b, f"analytics B should have eventCount"

        # Different sessions should have independent analytics
        # (Even if both have 0 events, they shouldn't share an in-memory cache)
        assert analytics_a is not analytics_b
    finally:
        _cleanup(sessions)


# ═══════════════════════════════════════════════════════════════════════
# Scenario 9 & 10: Empty sessionId must be rejected
# ═══════════════════════════════════════════════════════════════════════


def test_empty_session_id_rejected_get() -> None:
    """GET /profile with empty sessionId returns 422."""
    r = client.get("/api/profile", params={"sessionId": ""})
    assert r.status_code == 422, \
        f"empty sessionId GET should return 422, got {r.status_code}"
    detail = r.json().get("detail", {})
    assert "sessionId is required" in str(detail), \
        f"error should mention sessionId, got {detail}"


def test_empty_session_id_rejected_post() -> None:
    """POST /profile/build with empty sessionId returns 422."""
    r = client.post("/api/profile/build", json={
        "sessionId": "",
        "message": "我想学习人工智能导论",
    })
    assert r.status_code == 422, \
        f"empty sessionId POST should return 422, got {r.status_code}"
    detail = r.json().get("detail", {})
    assert "sessionId is required" in str(detail)


def test_empty_session_id_rejected_chat_send() -> None:
    """POST /chat/send with empty sessionId returns 422."""
    r = client.post("/api/chat/send", json={
        "sessionId": "",
        "message": "你好",
    })
    assert r.status_code == 422, \
        f"empty sessionId chat/send should return 422, got {r.status_code}"


def test_empty_session_id_rejected_chat_stream() -> None:
    """POST /chat/stream with empty sessionId returns 422."""
    r = client.post("/api/chat/stream", json={
        "sessionId": "",
        "message": "你好",
    })
    assert r.status_code == 422, \
        f"empty sessionId chat/stream should return 422, got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════
# Multi-session multi-subject: no data mixing across all dimensions
# ═══════════════════════════════════════════════════════════════════════


def test_multi_session_multi_subject_no_leak() -> None:
    """Comprehensive: 2 subjects x 2 sessions — profile/path/resources/analytics all isolated."""
    sessions_subjects = {
        "multi_s1": "ai_intro",
        "multi_s2": "ai_intro",
        "multi_s3": "data_structures",
        "multi_s4": "data_structures",
    }
    _cleanup(list(sessions_subjects.keys()))

    try:
        for sid, cid in sessions_subjects.items():
            agent_service.run_agents(
                session_id=sid,
                course_id=cid,
                user_message=f"我想学习{cid}",
            )

        db = SessionLocal()
        try:
            for sid, expected_course in sessions_subjects.items():
                path = get_latest_learning_path(db, sid)
                assert path is not None, f"session {sid} should have a path"
                assert path.session_id == sid, \
                    f"path.session_id ({path.session_id}) should == session ({sid})"
                assert path.course_id == expected_course, \
                    f"session {sid}: expected course {expected_course}, got {path.course_id}"

                profile = get_latest_profile(db, sid)
                assert profile is not None, f"session {sid} should have a profile"

                resources = get_resources(db, sid)
                for r in resources:
                    assert r.session_id == sid, \
                        f"resource {r.id} belongs to {r.session_id}, expected {sid}"
                    assert r.id.startswith(f"{sid}_"), \
                        f"resource id {r.id} should be prefixed with {sid}_"
        finally:
            db.close()

        # Cross-verify via API: no session can read another's path
        for sid, expected_course in sessions_subjects.items():
            r = client.get("/api/learning-path", params={"sessionId": sid})
            assert r.status_code == 200
            data = r.json()["data"]
            path_id = data.get("id") or data.get("path", {}).get("id", "")
            assert path_id.startswith(f"path_{sid}_"), \
                f"API: session {sid} path id should contain session id, got {path_id}"
    finally:
        _cleanup(list(sessions_subjects.keys()))


# ═══════════════════════════════════════════════════════════════════════
# Verify no hardcoded frontend_session_001 in app/ source
# ═══════════════════════════════════════════════════════════════════════


def test_no_frontend_session_001_in_app_source() -> None:
    """Verify that no app source file contains hardcoded frontend_session_001."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    violations: list[str] = []
    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "frontend_session_001" in content:
            violations.append(str(py_file.relative_to(app_dir.parent)))
    assert not violations, \
        f"Hardcoded frontend_session_001 found in: {violations}"


# ═══════════════════════════════════════════════════════════════════════
# Envelope structure validation
# ═══════════════════════════════════════════════════════════════════════


REQUIRED_ENVELOPE_FIELDS = {"status", "data", "message", "warnings", "source", "sessionId", "subjectId"}


def test_product_response_envelope_structure() -> None:
    """Verify that product endpoints return the unified envelope with all required fields."""
    session_id = f"envelope_{uuid.uuid4().hex[:6]}"
    _cleanup([session_id])

    try:
        agent_service.run_agents(
            session_id=session_id,
            course_id="data_structures",
            user_message="我是大二学生，想学数据结构",
        )

        # Profile envelope
        r = client.get("/api/profile", params={"sessionId": session_id})
        assert r.status_code == 200
        env = r.json()
        for field in REQUIRED_ENVELOPE_FIELDS:
            assert field in env, f"GET /profile: envelope missing field '{field}'"
        assert env["status"] == "success", f"GET /profile: expected status=success, got {env['status']}"
        assert "profile" in env["data"], f"GET /profile: data missing 'profile' key"
        assert env["sessionId"] == session_id, f"GET /profile: sessionId mismatch"
        assert isinstance(env["warnings"], list), "GET /profile: warnings should be a list"

        # Learning path envelope
        r = client.get("/api/learning-path", params={"sessionId": session_id})
        assert r.status_code == 200
        env = r.json()
        for field in REQUIRED_ENVELOPE_FIELDS:
            assert field in env, f"GET /learning-path: envelope missing field '{field}'"
        assert env["status"] == "success"
        assert "path" in env["data"], f"GET /learning-path: data missing 'path' key"

        # Resources envelope
        r = client.get("/api/resources", params={"sessionId": session_id})
        assert r.status_code == 200
        env = r.json()
        for field in REQUIRED_ENVELOPE_FIELDS:
            assert field in env, f"GET /resources: envelope missing field '{field}'"
        assert env["status"] == "success"
        assert "resources" in env["data"], f"GET /resources: data missing 'resources' key"
        assert "total" in env["data"], f"GET /resources: data missing 'total' key"

        # Analytics envelope
        r = client.get("/api/learning-analytics", params={"sessionId": session_id})
        assert r.status_code == 200
        env = r.json()
        for field in REQUIRED_ENVELOPE_FIELDS:
            assert field in env, f"GET /learning-analytics: envelope missing field '{field}'"
        assert env["status"] == "success"
        assert "eventCount" in env["data"], f"GET /learning-analytics: data missing 'eventCount' key"

        # Timeline envelope
        r = client.get("/api/learning-events/timeline", params={"sessionId": session_id})
        assert r.status_code == 200
        env = r.json()
        for field in REQUIRED_ENVELOPE_FIELDS:
            assert field in env, f"GET /learning-events/timeline: envelope missing field '{field}'"
        assert env["status"] == "success"
        assert "events" in env["data"], f"GET /learning-events/timeline: data missing 'events' key"

        # Empty profile session should also return envelope
        empty_id = f"envelope_empty_{uuid.uuid4().hex[:6]}"
        _cleanup([empty_id])
        r = client.get("/api/profile", params={"sessionId": empty_id})
        assert r.status_code == 200
        env = r.json()
        assert env["status"] == "success", f"empty profile: expected success, got {env}"
        assert env["source"] == "none", f"empty profile: expected source=none, got {env['source']}"
        assert "profile" in env["data"], f"empty profile: data should have profile"

    finally:
        _cleanup([session_id])


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    tests = [
        test_generated_data_is_readable_by_session_and_isolated,
        test_same_subject_different_sessions,
        test_different_subjects_different_sessions,
        test_cross_course_ai_first_then_ds,
        test_cross_course_ds_first_then_ai,
        test_profile_isolation_via_api,
        test_path_isolation_via_api,
        test_resources_isolation_via_api,
        test_analytics_isolation_via_api,
        test_empty_session_id_rejected_get,
        test_empty_session_id_rejected_post,
        test_empty_session_id_rejected_chat_send,
        test_empty_session_id_rejected_chat_stream,
        test_multi_session_multi_subject_no_leak,
        test_no_frontend_session_001_in_app_source,
        test_product_response_envelope_structure,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)
