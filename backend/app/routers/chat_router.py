"""Chat SSE endpoint — unified LangGraph entry point."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.conversation_state import conversation_store
from app.services.langgraph_orchestrator import run_pipeline

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
            state = dict(
                messages=[{"role": m["role"], "content": m["content"]} for m in state_obj.messages[-20:]],
                session_id=session_id,
                user_message=message,
                course_id=state_obj.facts.get("target_course"),
                profile_facts=dict(state_obj.facts),
            )

            result = run_pipeline(**state)

            reply = result.get("final_reply", "") or result.get("_conversation_reply", "") or "处理完成"
            for chunk in reply.splitlines(keepends=True):
                yield f"data: {json.dumps({'type':'messages','content':chunk}, ensure_ascii=False)}\n\n"

            conversation_store.append_message(session_id, "assistant", reply)
            if result:
                conversation_store.set_result(session_id, result)

            yield f"data: {json.dumps({'type':'done','sessionId':session_id,'pipeline_executed':True}, ensure_ascii=False)}\n\n"

        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=exc)
            yield f"data: {json.dumps({'type':'error','message':str(exc)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type':'done','error':str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
