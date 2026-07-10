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
    # ── 随学随新：每轮对话自动提取facts并更新画像 ──
    facts = result.get("_conversation_facts", {}) or {}
    if facts and isinstance(facts, dict):
        fact_map = {"background":"background","target_course":"target_course","knowledge_base":"knowledge_base",
                     "weak_points":"weak_points","learning_goal":"learning_goal","time_budget":"time_budget","preference":"preference"}
        for lk, fk in fact_map.items():
            v = str(facts.get(lk,"")).strip()
            if v and len(v)>=2 and v not in {"的是什么","什么","啥","未知","未提及","无","none"}:
                state_obj.facts[fk] = v
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


def _subject_id(payload: dict[str, Any]) -> str:
    return str(payload.get("subjectId") or payload.get("subject_id") or "").strip()


def _try_multimodal_chat(message: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    from app.routers.product import _classify_intent, _is_multimodal_request, _multimodal_chat_payload

    if not _is_multimodal_request(message, payload):
        return None

    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message, session_id)
    conversation_store.set_intent(session_id, intent)
    multimodal_payload = _multimodal_chat_payload(message, session_id, _subject_id(payload), payload, intent)
    if not multimodal_payload:
        return None

    reply = multimodal_payload["reply"]["content"]
    conversation_store.append_message(session_id, "assistant", reply)
    conversation_store.set_result(session_id, multimodal_payload)
    return multimodal_payload


def _multimodal_done_event(session_id: str, multimodal_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **_done_event(session_id, multimodal_payload),
        "agents_run": ["multimodal_agent"],
        "action": "multimodal",
        "workflow_trace": multimodal_payload.get("workflow_trace", {}),
        "multimodal_result": multimodal_payload.get("multimodal_result", {}),
        "intent_result": multimodal_payload.get("intent_result", {}),
        "final_reply_owner": "conversation_agent",
        "reply_source": "multimodal_agent",
        "fallback_used": False,
    }


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
            multimodal_payload = _try_multimodal_chat(message, session_id, payload)
            if multimodal_payload:
                reply = multimodal_payload["reply"]["content"]
                yield f"data: {json.dumps({'stage': '正在执行多模态任务', 'agentName': 'multimodal', 'progress': 80, 'done': False}, ensure_ascii=False)}\n\n"
                for chunk in reply.splitlines(keepends=True):
                    yield f"data: {json.dumps({'type': 'messages', 'content': chunk}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps(_multimodal_done_event(session_id, multimodal_payload), ensure_ascii=False)}\n\n"
                return

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
        multimodal_payload = _try_multimodal_chat(message, session_id, payload)
        if multimodal_payload:
            return {
                **multimodal_payload,
                **_multimodal_done_event(session_id, multimodal_payload),
            }

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
