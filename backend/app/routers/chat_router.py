"""Chat SSE streaming endpoint — the single main entry point for all agent interactions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.langgraph import EduAgentState, build_graph, get_checkpointer
from app.services.conversation_state import conversation_store
from app.services.learning_tracker import learning_tracker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


def _ensure_session(session_id: str) -> None:
    if not session_id or not session_id.strip():
        from app.utils.errors import MissingSessionIdError
        raise MissingSessionIdError()


@router.post("/api/chat/stream")
async def stream_chat(payload: dict[str, Any]) -> StreamingResponse:
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("sessionId", payload.get("session_id", f"sess_{int(time.time()*1000)}"))).strip()

    if not message:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type':'done','error':'empty message'}, ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream",
        )

    _ensure_session(session_id)
    conversation_store.append_message(session_id, "user", message)
    state_obj = conversation_store.get(session_id)

    async def event_stream():
        try:
            initial_state = EduAgentState(
                messages=[{"role": m["role"], "content": m["content"]} for m in state_obj.messages[-20:]],
                session_id=session_id,
                user_message=message,
                course_id=state_obj.facts.get("target_course"),
                profile_facts=dict(state_obj.facts),
            )

            checkpointer = await get_checkpointer()
            compiled = build_graph().compile(checkpointer=checkpointer) if checkpointer else build_graph().compile()
            config = {"configurable": {"thread_id": session_id}}

            final_state = await compiled.ainvoke(initial_state, config)
            state_data = final_state if isinstance(final_state, dict) else {}
            final_reply = state_data.get("final_reply", "")

            # stream reply
            if final_reply:
                for chunk in final_reply.splitlines(keepends=True):
                    yield f"data: {json.dumps({'type':'messages','content':chunk}, ensure_ascii=False)}\n\n"

            resources = state_data.get("resources") or []
            learning_path = state_data.get("learning_path") or []
            diagnosis = state_data.get("diagnosis") or {}

            conversation_store.append_message(session_id, "assistant", final_reply)
            conversation_store.set_result(session_id, state_data)

            done_event = {
                "type": "done",
                "sessionId": session_id,
                "pipeline_executed": bool(state_data.get("agent_trace")),
                "learning_path_created": bool(learning_path),
                "stage_count": len(learning_path) if isinstance(learning_path, list) else 0,
                "resources_created": bool(resources),
                "resource_count": len(resources) if isinstance(resources, list) else 0,
                "diagnosis_created": bool(diagnosis and diagnosis.get("weak_knowledge_points")),
                "fallback_used": not state_data.get("review_results", {}).get("passed", True),
                "final_reply_owner": "langgraph",
            }
            yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"

        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=exc)
            yield f"data: {json.dumps({'type':'error','message':str(exc)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type':'done','pipeline_executed':False}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
