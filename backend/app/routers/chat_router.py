"""Chat endpoints backed by the unified LangGraph pipeline."""

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


async def _run_chat(message: str, session_id: str) -> tuple[str, dict[str, Any]]:
    conversation_store.append_message(session_id, "user", message)
    state_obj = conversation_store.get(session_id)
    state = {
        "messages": [{"role": m["role"], "content": m["content"]} for m in state_obj.messages[-20:]],
        "session_id": session_id,
        "user_message": message,
        "course_id": state_obj.facts.get("target_course"),
        "profile_facts": dict(state_obj.facts),
        "feedback_signal": state_obj.feedback_signal,
    }

    result = await run_pipeline(**state)
    reply = result.get("final_reply", "") or result.get("_conversation_reply", "") or "处理完成"
    conversation_store.append_message(session_id, "assistant", reply)
    # Clear one-shot feedback signal after consumption
    if state_obj.feedback_signal is not None:
        state_obj.feedback_signal = None
    if result:
        conversation_store.set_result(session_id, result)
    return reply, result


def _done_event(session_id: str, result: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    event = {
        "type": "done",
        "done": True,
        "sessionId": session_id,
        "pipeline_executed": error is None,
        "learning_path_created": bool(result.get("learning_path")) if result else False,
        "resources_created": bool(result.get("resources")) if result else False,
        "questions_created": bool(result.get("questions")) if result else False,
    }
    if error:
        event["error"] = error
    return event


@router.post("/api/chat/stream")
async def stream_chat(payload: dict[str, Any]) -> StreamingResponse:
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("sessionId", payload.get("session_id", f"sess_{int(time.time() * 1000)}"))).strip()

    if not message:
        return StreamingResponse(
            iter([f"data: {json.dumps(_done_event(session_id, {}, 'empty message'), ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream",
        )

    _ensure_session(session_id)

    async def event_stream():
        try:
            reply, result = await _run_chat(message, session_id)
            for chunk in reply.splitlines(keepends=True):
                yield f"data: {json.dumps({'type': 'messages', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(_done_event(session_id, result), ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(_done_event(session_id, {}, str(exc)), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat/send")
async def send_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("sessionId", payload.get("session_id", f"sess_{int(time.time() * 1000)}"))).strip()
    if not message:
        return {"sessionId": session_id, "reply": None, "error": "empty message"}

    _ensure_session(session_id)
    try:
        reply, result = await _run_chat(message, session_id)
        return {
            "sessionId": session_id,
            "reply": {
                "id": f"assistant_{int(time.time() * 1000)}",
                "role": "assistant",
                "content": reply,
                "timestamp": int(time.time() * 1000),
            },
            **_done_event(session_id, result),
        }
    except Exception as exc:
        logger.error("Chat send error: %s", exc, exc_info=exc)
        return {"sessionId": session_id, "reply": None, "error": str(exc)}
