"""Core agent orchestration API endpoints.

Stage 2: Uses ``agent_service`` to trigger and track agent pipeline runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

from app.schemas.agent import AgentRunRequest
from app.schemas.common import ApiResponse
from app.services import agent_service
from app.utils.errors import MissingSessionIdError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])


@router.post("/agents/run")
def run_agents(payload: AgentRunRequest) -> dict[str, Any]:
    """Trigger the full multi-agent learning workflow.

    Returns the orchestrator result with per-agent step metadata,
    overall status, and generated profile / diagnosis / learning_path / resources.
    """
    session_id = payload.session_id.strip()
    if not session_id:
        raise MissingSessionIdError()
    course_id = payload.course_id

    try:
        result = agent_service.run_agents(
            session_id=session_id,
            user_message=payload.user_message,
            course_id=course_id,
        )

        return {
            "code": 0,
            "message": "success",
            "data": {
                "session_id": result.get("session_id", session_id),
                "course_id": result.get("course_id", course_id or ""),
                "overall_status": result.get("overall_status", "completed"),
                "overall_error": result.get("overall_error"),
                "profile": result.get("profile", {}),
                "diagnosis": result.get("diagnosis", {}),
                "learning_path": result.get("learning_path", []),
                "resources": result.get("resources", []),
                "knowledge_context": result.get("knowledge_context", {}),
                "review": result.get("review", {}),
                "agent_steps": result.get("agent_steps", []),
                "course": result.get("course"),
            },
            "request_id": f"req_agents_run_{int(time.time() * 1000)}",
        }
    except Exception as exc:
        logger.error("Agent orchestrator failed for session %s: %s", session_id, exc, exc_info=exc)
        return {
            "code": -1,
            "message": "Agent orchestrator failed, please try again",
            "data": None,
            "request_id": f"req_agents_run_{int(time.time() * 1000)}",
        }
