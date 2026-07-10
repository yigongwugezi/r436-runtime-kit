"""Chat endpoints backed by the unified LangGraph pipeline.

Streaming endpoint now uses run_pipeline_stream() to push per-agent
progress events to the frontend via SSE.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.conversation_state import conversation_store
from app.services.langgraph_orchestrator import run_pipeline, run_pipeline_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


def _ensure_session(session_id: str) -> None:
    if not session_id or not session_id.strip():
        from app.utils.errors import MissingSessionIdError
        raise MissingSessionIdError()


async def _run_chat(message: str, session_id: str) -> tuple[str, dict[str, Any]]:
    """Non-streaming path — kept for /api/chat/send."""
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
    if state_obj.feedback_signal is not None:
        state_obj.feedback_signal = None
    if result:
        conversation_store.set_result(session_id, result)
    return reply, result


async def _run_chat_stream(message: str, session_id: str):
    """Async generator: yield SSE event dicts from run_pipeline_stream."""
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

    final_reply = ""
    final_result: dict[str, Any] = {}
    structured_cards: list[dict[str, Any]] = []

    async for event in run_pipeline_stream(**state):
        yield event
        evt_type = event.get("type", "")
        if evt_type == "final_reply":
            final_reply = str(event.get("content", ""))
        elif evt_type == "agent_progress" and event.get("status") == "completed" and event.get("card"):
            # Collect structured cards for history metadata
            card = event.get("card", {})
            if card.get("card_type"):
                structured_cards.append({"card_type": card["card_type"],
                    "summary": card.get("summary", ""), "node": event.get("node", "")})
        elif evt_type == "awaiting_confirmation":
            preview = event.get("_preview_state") or {k: v for k, v in event.items() if k != "type"}
            state_obj = conversation_store.get(session_id)
            state_obj.preview_state = preview
        elif evt_type == "done":
            final_result = {k: v for k, v in event.items() if k != "type"}

    # Persist after stream completes — include card metadata in message
    if final_reply:
        msg = {"role": "assistant", "content": final_reply}
        if structured_cards:
            msg["cards"] = structured_cards
        conversation_store.append_message(session_id, "assistant", final_reply, cards=structured_cards or None)
    if state_obj.feedback_signal is not None:
        state_obj.feedback_signal = None
    if final_result:
        conversation_store.set_result(session_id, final_result)


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
            # ── Try multimodal first ──
            multimodal_payload = _try_multimodal_chat(message, session_id, payload)
            if multimodal_payload:
                yield f"data: {json.dumps({'stage': '正在执行多模态任务', 'agentName': 'multimodal', 'progress': 80, 'done': False}, ensure_ascii=False)}\n\n"
                reply = multimodal_payload["reply"]["content"]
                for chunk in reply.splitlines(keepends=True):
                    yield f"data: {json.dumps({'type': 'messages', 'content': chunk}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps(_multimodal_done_event(session_id, multimodal_payload), ensure_ascii=False)}\n\n"
                return

            # ── Stream pipeline with agent progress events ──
            final_reply_text = ""
            async for event in _run_chat_stream(message, session_id):
                evt_type = event.get("type", "")
                if evt_type == "agent_progress":
                    # Forward agent progress directly to frontend
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif evt_type == "final_reply":
                    final_reply_text = str(event.get("content", ""))
                elif evt_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': str(event.get('message', '')), 'done': False}, ensure_ascii=False)}\n\n"
                elif evt_type == "done":
                    # Stream final reply as text chunks, then send done event
                    if final_reply_text:
                        for chunk in final_reply_text.splitlines(keepends=True):
                            yield f"data: {json.dumps({'type': 'messages', 'content': chunk}, ensure_ascii=False)}\n\n"
                    result = {k: v for k, v in event.items() if k != "type"}
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


@router.post("/api/chat/confirm")
async def confirm_preview(payload: dict[str, Any]) -> StreamingResponse:
    """Resume a paused full_workflow after user confirms/adjusts the preview.

    Expects: {"sessionId": "...", "action": "confirm"|"adjust"|"cancel", "message": "调整说明"}
    Returns: SSE stream with Phase 2 progress events.
    """
    import time as _time
    session_id = str(payload.get("sessionId", payload.get("session_id", ""))).strip()
    action = str(payload.get("action", "confirm")).strip()
    adjust_message = str(payload.get("message", "")).strip()

    if not session_id:
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'message': 'missing sessionId'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    state_obj = conversation_store.get(session_id)
    preview_state = state_obj.preview_state

    if action == "cancel" or not preview_state:
        async def _cancel():
            yield f"data: {json.dumps({'type': 'agent_progress', 'node': 'cancelled', 'agent_name': 'ConversationAgent', 'label': '已取消', 'status': 'completed', 'summary': '学生取消了生成'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'final_reply', 'content': '好的，已取消。如果你改变主意，随时告诉我。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'done': True, 'sessionId': session_id, 'pipeline_executed': False}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_cancel(), media_type="text/event-stream")

    if action == "adjust" and adjust_message:
        # Re-run planner with adjustment feedback, then resume
        from app.services.langgraph_orchestrator import resume_pipeline_stream
        # Inject adjustment into preview state
        preview_state["user_message"] = f"{preview_state.get('user_message', '')}\n学生调整要求：{adjust_message}"
        preview_state["mode"] = "adjust"
        # Let planner re-run with adjustment
        from app.services.agent_factory import AgentFactory
        factory = AgentFactory()
        state_obj.preview_state = None

        async def _adjust_stream():
            yield f"data: {json.dumps({'type': 'agent_progress', 'node': 'planner', 'agent_name': 'PlannerAgent', 'label': '重新规划', 'status': 'started'}, ensure_ascii=False)}\n\n"
            # Re-run planner in adjust mode
            from app.services.langgraph_orchestrator import _run_agent as _ra
            state = dict(preview_state, _factory=factory)
            await _ra("planner", state, factory)
            yield f"data: {json.dumps({'type': 'agent_progress', 'node': 'planner', 'agent_name': 'PlannerAgent', 'label': '重新规划', 'status': 'completed', 'summary': '调整完成'}, ensure_ascii=False)}\n\n"
            # Resume with Phase 2
            async for event in resume_pipeline_stream(state, factory):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            # Persist
            final_reply = state.get("final_reply", "")
            if final_reply:
                conversation_store.append_message(session_id, "assistant", final_reply)
            conversation_store.set_result(session_id, state)

        return StreamingResponse(_adjust_stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # action == "confirm"
    from app.services.langgraph_orchestrator import resume_pipeline_stream
    from app.services.agent_factory import AgentFactory
    factory = AgentFactory()
    state_obj.preview_state = None

    async def _confirm_stream():
        state = dict(preview_state, _factory=factory)
        async for event in resume_pipeline_stream(state, factory):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        # Persist
        final_reply = state.get("final_reply", "")
        if final_reply:
            conversation_store.append_message(session_id, "assistant", final_reply)
        conversation_store.set_result(session_id, state)

    return StreamingResponse(_confirm_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/nav-state")
async def nav_state(sessionId: str = "") -> dict[str, Any]:
    """Return left-nav badge counts and recent output summaries.

    Called by the frontend on page load to populate:
      - Profile completion ring
      - Diagnosis weak-point count badge
      - Path new-recommendation dot
      - Review warning/blocked count badge
    """
    if not sessionId:
        return {"badges": {}, "recent": {}}
    _ensure_session(sessionId)
    state_obj = conversation_store.get(sessionId)
    result = state_obj.last_result or {}
    diagnosis = result.get("diagnosis", {}) if isinstance(result, dict) else {}
    review = result.get("review", {}) if isinstance(result, dict) else {}
    path = result.get("learning_path") or result.get("stages") or []
    profile = result.get("profile", {}) if isinstance(result, dict) else {}

    weak = diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []
    review_checks = review.get("checks", [])
    profile_filled = sum(1 for v in (profile.values() if isinstance(profile, dict) else [])
                         if isinstance(v, dict) and str(v.get("value", "")).strip()
                         and str(v.get("value", "")) != "待补充")

    return {
        "badges": {
            "profile_filled": profile_filled,
            "profile_total": 9,
            "diagnosis_weak_count": len(weak),
            "diagnosis_high_count": sum(1 for w in weak if w.get("priority") == "high"),
            "path_has_new": len(path) > 0,
            "path_has_adjustment": state_obj.feedback_signal is not None,
            "review_warning_count": sum(1 for c in review_checks if c.get("status") == "warning"),
            "review_blocked_count": sum(1 for c in review_checks if c.get("status") == "blocked"),
        },
        "recent": {
            "has_profile": profile_filled > 0,
            "has_diagnosis": len(weak) > 0,
            "has_path": len(path) > 0,
            "has_resources": bool(result.get("resources")),
            "has_report": bool(review),
            "last_intent": state_obj.last_intent.get("action") if state_obj.last_intent else None,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Center-area content endpoints — frontend queries structured data independently
# ═══════════════════════════════════════════════════════════════════════════════


def _get_last_result(session_id: str) -> dict[str, Any]:
    state_obj = conversation_store.get(session_id)
    return state_obj.last_result or {}


@router.get("/api/content/profile")
async def content_profile(sessionId: str = "") -> dict[str, Any]:
    """Return latest profile data for the profile floating panel (§2.4.2)."""
    if not sessionId:
        return {"profile": {}, "dimensions": []}
    _ensure_session(sessionId)
    result = _get_last_result(sessionId)
    profile = result.get("profile", {}) if isinstance(result, dict) else {}
    dimensions = []
    if isinstance(profile, dict):
        for k, v in profile.items():
            if isinstance(v, dict):
                dimensions.append({"key": k, "label": v.get("label", k),
                    "value": v.get("value", ""), "score": v.get("score", 0),
                    "confidence": v.get("confidence", 0), "explanation": v.get("explanation", ""),
                    "evidence": v.get("evidence", ""), "source": v.get("source", "")})
    filled = sum(1 for d in dimensions if d["value"] and d["value"] != "待补充")
    return {"profile": profile, "dimensions": dimensions, "filled": filled, "total": 9}


@router.get("/api/content/diagnosis")
async def content_diagnosis(sessionId: str = "") -> dict[str, Any]:
    """Return latest diagnosis data for the diagnosis page (§6.3)."""
    if not sessionId:
        return {"diagnosis": {}}
    _ensure_session(sessionId)
    result = _get_last_result(sessionId)
    diagnosis = result.get("diagnosis", {}) if isinstance(result, dict) else {}
    weak = diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []
    mastery = diagnosis.get("mastery_levels") or []
    evidence_chain = diagnosis.get("evidence_chain") or []
    return {
        "diagnosis": diagnosis,
        "weak_points": weak,
        "mastery_levels": mastery,
        "evidence_chain": evidence_chain,
        "overall_confidence": diagnosis.get("confidence", 0),
        "needs_more_evidence": diagnosis.get("needs_more_evidence", False),
        "risk_flags": diagnosis.get("risk_flags", []),
        "high_count": sum(1 for w in weak if w.get("priority") == "high"),
    }


@router.get("/api/content/path")
async def content_path(sessionId: str = "") -> dict[str, Any]:
    """Return latest learning path data for the path map page (§7.4)."""
    if not sessionId:
        return {"stages": [], "review_tasks": []}
    _ensure_session(sessionId)
    result = _get_last_result(sessionId)
    stages = result.get("learning_path") or result.get("stages") or []
    review_tasks = result.get("review_tasks") or []
    return {
        "stages": stages,
        "review_tasks": review_tasks,
        "estimated_days": result.get("estimatedDays", 0),
        "stage_rationales": result.get("stage_rationales", []),
        "planner_metadata": result.get("planner_metadata", {}),
        "risk_flags": result.get("risk_flags", []),
        "needs_more_diagnosis": result.get("needs_more_diagnosis", False),
    }


@router.get("/api/content/resources")
async def content_resources(sessionId: str = "") -> dict[str, Any]:
    """Return latest resources for the resource display area (§8.3)."""
    if not sessionId:
        return {"resources": []}
    _ensure_session(sessionId)
    result = _get_last_result(sessionId)
    resources = result.get("resources") or []
    return {
        "resources": resources,
        "by_type": _count_by_type(resources),
        "by_quality": _count_by_quality(resources),
        "by_stage": _group_by_stage(resources),
    }


@router.get("/api/content/report")
async def content_report(sessionId: str = "") -> dict[str, Any]:
    """Return latest report data for the report page (Chapter 12)."""
    if not sessionId:
        return {"review": {}, "grading": {}, "diagnosis": {}}
    _ensure_session(sessionId)
    result = _get_last_result(sessionId)
    review = result.get("review", {}) if isinstance(result, dict) else {}
    grading = result.get("grading_result", {}) if isinstance(result, dict) else {}
    diagnosis = result.get("diagnosis", {}) if isinstance(result, dict) else {}
    review_checks = review.get("checks", [])
    return {
        "review": review,
        "review_checks": review_checks,
        "quality_status": review.get("quality_status", ""),
        "anti_hallucination": review.get("anti_hallucination", {}),
        "review_passed": sum(1 for c in review_checks if c.get("status") == "passed"),
        "review_warning": sum(1 for c in review_checks if c.get("status") == "warning"),
        "review_blocked": sum(1 for c in review_checks if c.get("status") == "blocked"),
        "grading_result": grading,
        "diagnosis_weak": (diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []),
        "diagnosis_mastery": diagnosis.get("mastery_levels") or [],
    }


def _count_by_type(resources: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in resources:
        t = str(r.get("type", "unknown"))
        counts[t] = counts.get(t, 0) + 1
    return counts


def _count_by_quality(resources: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in resources:
        q = str(r.get("quality_status", "unknown"))
        counts[q] = counts.get(q, 0) + 1
    return counts


def _group_by_stage(resources: list) -> dict[str, list]:
    groups: dict[str, list] = {}
    for r in resources:
        sid = str(r.get("related_stage_id", "_unlinked"))
        groups.setdefault(sid, []).append({"resource_id": r.get("resource_id", ""),
            "type": r.get("type", ""), "title": r.get("title", ""),
            "quality_status": r.get("quality_status", "")})
    return groups
