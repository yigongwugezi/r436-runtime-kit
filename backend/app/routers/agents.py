from fastapi import APIRouter

from app.schemas.agent import AgentRunRequest
from app.schemas.common import ApiResponse
from app.services.orchestrator import AgentOrchestrator


router = APIRouter(tags=["agents"])


@router.post("/agents/run")
def run_agents(payload: AgentRunRequest) -> ApiResponse[dict]:
    result = AgentOrchestrator().run(
        session_id=payload.session_id,
        course_id=payload.course_id,
        user_message=payload.user_message,
    )
    return ApiResponse(data=result, request_id="req_agents_run")
