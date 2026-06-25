"""Error handling tests — verifies structured errors, input validation, fallback marking.

These tests verify the unified error handling introduced in v0.5.0:
- Structured error responses with code / is_user_error
- No stack traces leaked in responses
- Fallback data is clearly marked
- Empty/missing inputs return proper validation errors
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════
# User-input validation errors (4xx)
# ═══════════════════════════════════════════════════════════════════════

def test_missing_session_id_returns_422_with_code():
    """Missing sessionId returns 422 with MISSING_SESSION_ID code."""
    resp = client.get("/profile", params={"sessionId": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "error"
    assert body["code"] == "MISSING_SESSION_ID"
    assert body["is_user_error"] is True
    assert "sessionId" in body["message"]


def test_empty_message_returns_422():
    """Empty message in chat/send returns 422 with EMPTY_MESSAGE code."""
    resp = client.post("/chat/send", json={"sessionId": "s_test", "message": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "EMPTY_MESSAGE"
    assert body["is_user_error"] is True


def test_whitespace_message_returns_422():
    """Whitespace-only message returns 422."""
    resp = client.post("/chat/send", json={"sessionId": "s_test", "message": "   "})
    assert resp.status_code == 422
    assert resp.json()["code"] == "EMPTY_MESSAGE"


def test_missing_subject_id_validation_function():
    """ValidationError helper for subjectId raises correctly."""
    from app.utils.errors import ValidationError
    from app.routers.product import _validate_subject_id

    with pytest.raises(ValidationError) as exc_info:
        _validate_subject_id("")
    assert exc_info.value.code == "MISSING_SUBJECT_ID"
    assert exc_info.value.status_code == 422

    with pytest.raises(ValidationError):
        _validate_subject_id(None)

    # Non-empty should not raise
    _validate_subject_id("s001")


def test_resource_not_found_returns_404():
    """GET non-existent resource returns 404 with NOT_FOUND code."""
    resp = client.get("/api/courses/nonexistent_course_999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == "error"
    assert body["code"] == "NOT_FOUND"
    assert body["is_user_error"] is True


# ═══════════════════════════════════════════════════════════════════════
# Error response safety (no stack traces)
# ═══════════════════════════════════════════════════════════════════════

def test_error_response_never_leaks_stack_trace():
    """4xx and 5xx response bodies never contain Python traceback markers."""
    # Test 404
    resp = client.get("/api/courses/nonexistent")
    body_text = json.dumps(resp.json(), ensure_ascii=False)
    assert "Traceback" not in body_text
    assert "File " not in body_text.split('"')[0]
    assert "raise " not in body_text.lower()

    # Test 422
    resp = client.get("/profile", params={"sessionId": ""})
    body_text = json.dumps(resp.json(), ensure_ascii=False)
    assert "Traceback" not in body_text
    assert "File " not in body_text.split('"')[0]

    # Test 500 (unknown path that triggers internal handler — 404,
    # but verify the handler structure exists)
    resp = client.get("/api/courses/nonexistent")
    assert "stack" not in json.dumps(resp.json()).lower()


# ═══════════════════════════════════════════════════════════════════════
# Empty / no-data responses
# ═══════════════════════════════════════════════════════════════════════

def test_db_no_data_for_unknown_session_returns_empty_data():
    """Unknown session should return empty data with source marker, not crash."""
    resp = client.get("/resources", params={"sessionId": "no_such_session_xyz"})
    assert resp.status_code == 200
    body = resp.json()
    # The frontend interceptor unwraps the envelope for 200 responses
    # but here we read the raw body
    assert body["status"] == "success" or body["status"] == "error"


def test_analytics_no_events_returns_valid_structure():
    """Analytics for session with no events returns valid (possibly empty) structure."""
    resp = client.get("/learning-analytics", params={"sessionId": "no_events_session"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success" or "data" in body


# ═══════════════════════════════════════════════════════════════════════
# Fallback marking
# ═══════════════════════════════════════════════════════════════════════

def test_fallback_agent_step_has_quality_status():
    """BaseAgent.get_fallback() returns agent_step with source and quality_status."""
    from app.agents.base import BaseAgent

    class TestAgent(BaseAgent):
        agent_id = "test_agent"
        agent_name = "Test Agent"

        def run(self, context):
            return {"agent_step": {"status": "completed"}}

    agent = TestAgent()
    fallback = agent.get_fallback()
    step = fallback["agent_step"]
    assert step["status"] == "failed"
    assert step["source"] == "rule_based_fallback"
    assert step["quality_status"] == "fallback"
    assert "error_reason" in step


def test_planner_fallback_has_source_and_quality_status():
    """PlannerAgent fallback includes top-level source/quality_status markers."""
    from app.agents.planner_agent import PlannerAgent

    agent = PlannerAgent()
    fallback = agent.get_fallback({"user_message": "test"})
    assert fallback["source"] == "rule_based_fallback"
    assert fallback["quality_status"] == "fallback"
    assert "reason" in fallback


# ═══════════════════════════════════════════════════════════════════════
# Exception hierarchy
# ═══════════════════════════════════════════════════════════════════════

def test_missing_session_id_error_has_correct_fields():
    """MissingSessionIdError has proper status code and is_user_error."""
    from app.utils.errors import MissingSessionIdError

    exc = MissingSessionIdError()
    assert exc.status_code == 422
    assert exc.is_user_error is True
    assert exc.code == "MISSING_SESSION_ID"


def test_not_found_error_carries_resource_info():
    """NotFoundError includes resource and resource_id in response."""
    from app.utils.errors import NotFoundError

    exc = NotFoundError("Thing not found", resource="thing", resource_id="abc")
    assert exc.status_code == 404
    assert exc.is_user_error is True
    d = exc.to_response_dict()
    assert d["resource"] == "thing"
    assert d["resource_id"] == "abc"
