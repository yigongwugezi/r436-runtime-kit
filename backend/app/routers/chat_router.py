"""Chat endpoints backed by the unified LangGraph pipeline."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.services.conversation_state import conversation_store
from app.services.langgraph_orchestrator import run_pipeline
from app.db.engine import SessionLocal
from app.db.models import SessionModel
from app.db.repository import get_or_create_session
from app.middleware.auth import AuthContext, get_auth
from app.services.subject_identity import bind_explicit_subject_to_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


_SECTION_RESOURCE_REQUESTS = {
    "summary_card": ("生成总结卡片", "生成总结卡", "生成总结"),
    "concept_comparison": ("生成概念对比", "生成概念比较"),
    "worked_example": ("生成例题详解", "生成例题"),
    "mistake_checklist": ("生成易错点清单", "生成易错清单"),
    "review_notes": ("生成复习笔记",),
    "knowledge_map": ("生成知识结构图", "生成知识图谱"),
    "process_flow": ("生成学习流程图", "生成过程流程图"),
    "concept_diagram": ("生成概念对比图", "生成概念关系图"),
    "execution_trace": ("生成执行过程图", "生成执行轨迹"),
    "code_trace": ("生成代码运行轨迹", "生成代码执行轨迹"),
}
_SECTION_RESOURCE_GUIDANCE = "请先进入一个小节的讲义页面，再生成对应的学习资源。"


def _section_resource_types(message: str) -> list[str]:
    """Return requested section-resource types without entering the main pipeline."""
    normalized = re.sub(r"\s+", "", message)
    if "生成本节资源" in normalized or "生成本节学习资源" in normalized:
        return list(_SECTION_RESOURCE_REQUESTS)
    return [
        resource_type
        for resource_type, phrases in _SECTION_RESOURCE_REQUESTS.items()
        if any(phrase in normalized for phrase in phrases)
    ]


def _section_context(payload: dict[str, Any]) -> dict[str, Any] | None:
    current = payload.get("currentSection") or payload.get("current_section") or {}
    current = current if isinstance(current, dict) else {}
    section_id = str(payload.get("sectionId") or payload.get("section_id") or current.get("id") or "").strip()
    if not section_id:
        return None
    return {
        "sectionId": section_id,
        "sectionTitle": str(payload.get("sectionTitle") or payload.get("section_title") or current.get("title") or "").strip(),
        "pathId": str(payload.get("pathId") or payload.get("path_id") or "").strip(),
        "stageId": str(payload.get("stageId") or payload.get("stage_id") or "").strip(),
        "chapterId": str(payload.get("chapterId") or payload.get("chapter_id") or "").strip(),
        "knowledgePoints": payload.get("knowledgePoints") or payload.get("knowledge_points") or current.get("knowledgePoints") or [],
        "lectureContent": str(payload.get("lectureContent") or payload.get("lecture_content") or ""),
    }


def _try_section_resource_chat(message: str, session_id: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    resource_types = _section_resource_types(message)
    if not resource_types:
        return None

    conversation_store.append_message(session_id, "user", message)
    state = conversation_store.get(session_id)
    context = _section_context(payload)
    result = dict(state.last_result or {})
    result["action"] = "section_generated_resource"

    if context is None:
        reply = _SECTION_RESOURCE_GUIDANCE
        result["section_resource_request"] = {"status": "needs_section_context", "resource_types": resource_types}
    else:
        # Reuse the existing section endpoint so generation and persistence stay identical.
        from app.routers.product import generate_section_resource

        generated = []
        for resource_type in resource_types:
            response = generate_section_resource(
                context["sectionId"],
                {"sessionId": session_id, "resourceType": resource_type, **context},
            )
            resource = (response.get("data") or {}).get("resource") if isinstance(response, dict) else None
            if resource:
                generated.append(resource)

        if generated:
            names = "、".join(str(item.get("title") or "学习资源") for item in generated)
            reply = f"已为当前小节生成：{names}。"
            result["section_resource_request"] = {"status": "completed", "resources": generated}
        else:
            reply = "当前小节资源生成失败，请稍后重试。"
            result["section_resource_request"] = {"status": "failed", "resource_types": resource_types}

    conversation_store.append_message(session_id, "assistant", reply)
    conversation_store.set_result(session_id, result)
    return reply, result


def _auto_save_profile(state_obj: Any) -> None:
    """Persist current facts as a profile snapshot after every message."""
    facts = getattr(state_obj, "facts", {}) or {}
    if not facts:
        return
    dims = []
    label_map = {
        "background": ("身份/专业背景", "background"),
        "target_course": ("目标课程", "target_course"),
        "knowledge_base": ("已有基础", "knowledge_base"),
        "weak_points": ("薄弱点", "weak_points"),
        "learning_goal": ("学习目标", "learning_goal"),
        "time_budget": ("时间安排", "time_budget"),
        "preference": ("学习偏好", "preference"),
    }
    for key, (label, _) in label_map.items():
        val = str(facts.get(key, "")).strip()
        if val and val not in ("未提及", "待补充", "未知", "", "无"):
            dims.append({"key": key, "label": label, "value": val, "score": 60, "confidence": 0.8, "source": "conversation_extract"})
    if not dims:
        return
    try:
        from app.routers.product import _profile_v2, _save_profile_v2

        profile_v2 = _profile_v2(state_obj.session_id)
        _save_profile_v2(state_obj.session_id, profile_v2, {"dimensions": dims})
    except Exception:
        pass


def _ensure_session(session_id: str, learner_id: str = "", subject_id: str = "") -> None:
    if not session_id or not session_id.strip():
        from app.utils.errors import MissingSessionIdError

        raise MissingSessionIdError()
    db = SessionLocal()
    try:
        get_or_create_session(db, session_id, learner_id=learner_id or None, subject_id=subject_id or None, require_learner=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="session belongs to another learner") from exc
    finally:
        db.close()


def _bind_current_subject_from_message(state_obj: Any) -> dict[str, Any] | None:
    """Bind only an unscoped session whose current message named a subject."""
    if "target_course" not in getattr(state_obj, "last_updated_fields", set()):
        return None
    name = str(getattr(state_obj, "facts", {}).get("target_course") or "").strip()
    if not name:
        return None
    db = SessionLocal()
    try:
        session = db.get(SessionModel, state_obj.session_id)
        learner_id = str((session.learner_id if session else "") or "")
        subject = bind_explicit_subject_to_session(db, state_obj.session_id, learner_id, name)
        if subject is None:
            return None
        return {
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "created_at": int(subject.created_at.timestamp() * 1000) if subject.created_at else 0,
            "updated_at": int(subject.updated_at.timestamp() * 1000) if subject.updated_at else 0,
        }
    except Exception:
        db.rollback()
        logger.warning("Could not bind explicit subject for session=%s", state_obj.session_id)
        return None
    finally:
        db.close()


async def _run_chat(message: str, session_id: str, search_enabled: bool = False, deep_think_enabled: bool = False, chat_mode: str = "free") -> tuple[str, str, dict[str, Any]]:
    # ── 自由模式：纯问答，零副作用，不走任何 Agent 管道 ──
    if chat_mode == "free" and _is_chat_quick(message, None, deep_think_enabled, chat_mode):
        from app.services.deeptutor_facade import deeptutor
        try:
            if deep_think_enabled:
                from app.config import settings
                from app.services.llm_client import get_llm_client
                raw = get_llm_client(settings.llm_provider).chat(messages=[{"role": "user", "content": message}], temperature=0.7, reasoning=True)
                reply = raw
                thinking = ""
                s = raw.find("<thinking>")
                e = raw.rfind("</thinking>")
                if s >= 0 and e > s:
                    thinking = raw[s + 10:e]
                    reply = raw[e + 11:].strip()
            else:
                reply = await deeptutor.chat(message, [], profile_context="", persona_context="")
        except Exception:
            reply = "你好！我是EduAgent，有什么可以帮你的？"
            thinking = ""
        conversation_store.append_message(session_id, "assistant", reply)
        return reply, thinking if deep_think_enabled else "", {}

    # ── 规划模式：走完整链路 ──
    conversation_store.append_message(session_id, "user", message)
    state_obj = conversation_store.get(session_id)
    # ── Log extracted facts for debugging profile capture ──
    facts_before = dict(state_obj.facts)
    filled = {k: v for k, v in facts_before.items() if v and str(v).strip()}
    logger.info(
        "Profile facts after extract: session=%s filled=%d/%d facts=%s",
        session_id, len(filled), 7,
        {k: str(v)[:40] for k, v in filled.items()},
    )

    # ── 检查评估闭环通知：路径/画像是否在后台被更新了 ──
    assessment_context = ""
    try:
        from app.services.assessment_loop import notification_store
        pending = notification_store.pop_all(session_id)
        if pending:
            path_adjusted = any(n["type"] == "plan_adjusted" for n in pending)
            diagnosis_updated = any(n["type"] == "diagnosis_updated" for n in pending)
            resource_ready = any(n["type"] == "recommendations_ready" for n in pending)
            if path_adjusted or diagnosis_updated:
                parts = ["【系统通知：上次学习后发生了以下变化，请在回复中自然地提及】"]
                for n in pending:
                    parts.append(f"- {n['title']}：{n['message']}")
                assessment_context = "\n".join(parts)
                logger.info(
                    "Injecting assessment context for session=%s: path_adj=%s diag=%s res=%s",
                    session_id, path_adjusted, diagnosis_updated, resource_ready,
                )
    except Exception:
        pass

    messages_raw = [{"role": m["role"], "content": m["content"]} for m in state_obj.messages[-20:]]
    if assessment_context:
        messages_raw.append({"role": "system", "content": assessment_context})

    state = {
        "messages": messages_raw,
        "session_id": session_id,
        "user_message": message,
        "course_id": state_obj.facts.get("target_course"),
        "profile_facts": dict(state_obj.facts),
        "feedback_signal": state_obj.feedback_signal,
        "search_enabled": search_enabled,
        "deep_think_enabled": deep_think_enabled,
    }
    try:
        from app.routers.product import _profile_v2
        state["profile_v2"] = _profile_v2(session_id)
    except Exception:
        state["profile_v2"] = {}

    # ── 注入后台评估闭环更新的完整结构化画像 ──
    last = state_obj.last_result or {}
    if isinstance(last.get("profile"), dict) and last["profile"]:
        state["profile"] = last["profile"]
    if isinstance(last.get("diagnosis"), dict) and last["diagnosis"]:
        state["diagnosis"] = last["diagnosis"]
    # 如果后台调整了路径，注入最新的（避免聊天流程用旧数据）
    if isinstance(last.get("learning_path"), list) and last["learning_path"]:
        state["learning_path"] = last["learning_path"]
        state["existing_path"] = {"stages": last["learning_path"]}


    result = await run_pipeline(**state)
    reply = result.get("final_reply", "") or result.get("_conversation_reply", "") or "处理完成"
    thinking = result.get("_conversation_thinking", "") or ""
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
    current_subject = _bind_current_subject_from_message(state_obj)
    if current_subject:
        result["current_subject"] = current_subject
    # ── Auto-persist profile snapshot after every message ──
    _auto_save_profile(state_obj)
    # Clear one-shot feedback signal after consumption, store new signal for next request
    if state_obj.feedback_signal is not None:
        state_obj.feedback_signal = None
    new_signal = result.get("feedback_signal")
    if new_signal is not None:
        state_obj.feedback_signal = new_signal
    if result:
        conversation_store.set_result(session_id, result)
    return reply, thinking, result


def _done_event(session_id: str, result: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    event = {
        "type": "done",
        "done": True,
        "sessionId": session_id,
        "pipeline_executed": error is None,
        "agents_run": result.get("agents_run") or [],
        "current_agent": result.get("current_agent") or "",
        "progress": result.get("progress") or {},
        "learning_path_created": bool(result.get("learning_path")),
        "learning_path_adjusted": bool(result.get("path_adjusted")),
        "resources_created": bool(result.get("resources")),
        "questions_created": bool(result.get("questions")),
        "multimodal_result": result.get("multimodal_result") or {},
        "diagnosis_result": result.get("diagnosis_result") or result.get("diagnosis") or {},
        "planner_metadata": result.get("planner_metadata") or {},
        "warnings": result.get("warnings") or [],
        "fallback_used": bool(result.get("fallback_used")),
        "current_subject": result.get("current_subject") or None,
        "resources_summary": [
            {"id": r.get("id", r.get("resource_id", "")), "type": r.get("type", "lecture"), "title": r["title"],
             "description": r.get("description", r.get("content", ""))[:120]}
            for r in (result.get("resources") or []) if isinstance(r, dict) and r.get("title")
        ],
        "suggested_actions": result.get("_conversation_suggestions") or [],
    }
    if error:
        event["error"] = error
    return event


def _subject_id(payload: dict[str, Any]) -> str:
    return str(payload.get("subjectId") or payload.get("subject_id") or "").strip()


def _learner_id(payload: dict[str, Any], auth: AuthContext) -> str:
    if not auth.is_authenticated:
        return ""
    requested = str(payload.get("learnerId") or payload.get("learner_id") or "").strip()
    if requested and requested != auth.learner_id:
        raise HTTPException(status_code=403, detail="learnerId does not match the authenticated user")
    return auth.learner_id


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
    _auto_save_profile(conversation_store.get(session_id))
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
async def stream_chat(payload: dict[str, Any], auth: AuthContext = Depends(get_auth)) -> StreamingResponse:
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("sessionId", payload.get("session_id", f"sess_{int(time.time() * 1000)}"))).strip()

    if not message:
        return StreamingResponse(
            iter([f"data: {json.dumps(_done_event(session_id, {}, 'empty message'), ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream",
        )

    _ensure_session(session_id, _learner_id(payload, auth), _subject_id(payload))

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

            section_resource_result = _try_section_resource_chat(message, session_id, payload)
            if section_resource_result:
                reply, result = section_resource_result
                for chunk in reply.splitlines(keepends=True):
                    yield f"data: {json.dumps({'type': 'messages', 'content': chunk}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps(_done_event(session_id, result), ensure_ascii=False)}\n\n"
                return

            search_enabled = bool(payload.get("search_enabled", False))
            deep_think_enabled = bool(payload.get("deep_think_enabled", False))
            chat_mode = str(payload.get("chat_mode", "free"))
            # ── 自由模式流式直调 ──
            if chat_mode == "free" and message and not any(kw in message for kw in ["生成", "出题", "规划", "路径"]):
                from app.services.llm_client import get_llm_client
                from app.config import settings
                client = get_llm_client(settings.llm_provider)
                deep_think = bool(payload.get("deep_think_enabled", False))
                reasoning_chunks = []
                for token in client.stream_chat([{"role": "user", "content": message}], reasoning=deep_think):
                    yield f"data: {json.dumps({'type': 'messages', 'content': token}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps(_done_event(session_id, {}), ensure_ascii=False)}\n\n"
                conversation_store.append_message(session_id, "assistant", message)
                return
            reply, thinking, result = await _run_chat(message, session_id, search_enabled=search_enabled, deep_think_enabled=deep_think_enabled, chat_mode=chat_mode)
            if thinking:
                yield f"data: {json.dumps({'reasoning': thinking}, ensure_ascii=False)}\n\n"
            for chunk in reply.splitlines(keepends=True):
                yield f"data: {json.dumps({'type': 'messages', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(_done_event(session_id, result), ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=exc)
            error_message = "学习方案生成失败，请稍后重试。"
            yield f"data: {json.dumps({'type': 'error', 'message': error_message}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(_done_event(session_id, {}, error_message), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat/send")
async def send_chat(payload: dict[str, Any], auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("sessionId", payload.get("session_id", f"sess_{int(time.time() * 1000)}"))).strip()
    if not message:
        return {"sessionId": session_id, "reply": None, "error": "empty message"}

    _ensure_session(session_id, _learner_id(payload, auth), _subject_id(payload))
    try:
        multimodal_payload = _try_multimodal_chat(message, session_id, payload)
        if multimodal_payload:
            return {
                **multimodal_payload,
                **_multimodal_done_event(session_id, multimodal_payload),
            }

        section_resource_result = _try_section_resource_chat(message, session_id, payload)
        if section_resource_result:
            reply, result = section_resource_result
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

        search_enabled = bool(payload.get("search_enabled", False))
        deep_think_enabled = bool(payload.get("deep_think_enabled", False))
        chat_mode = str(payload.get("chat_mode", "free"))
        reply, thinking, result = await _run_chat(message, session_id, search_enabled=search_enabled, deep_think_enabled=deep_think_enabled, chat_mode=chat_mode)
        return {
            "sessionId": session_id,
            "reply": {
                "id": f"assistant_{int(time.time() * 1000)}",
                "role": "assistant",
                "content": reply,
                "reasoningContent": thinking,
                "timestamp": int(time.time() * 1000),
            },
            **_done_event(session_id, result),
        }
    except Exception as exc:
        logger.error("Chat send error: %s", exc, exc_info=exc)
        return {"sessionId": session_id, "reply": None, "error": "学习方案生成失败，请稍后重试。"}
