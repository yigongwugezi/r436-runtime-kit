"""Product-facing API routes for the EduAgent frontend.

Design principles (Stage 2):
- **Read endpoints** (GET) read directly from the database — they NEVER trigger agent runs.
- **Write/trigger endpoints** (POST) call ``agent_service.run_agents()``, persist results, and return them.
- All responses use the unified ``_product_response()`` envelope with fields:
  ``status``, ``data``, ``message``, ``warnings``, ``source``, ``sessionId``, ``subjectId``.
- Every endpoint requires ``sessionId`` — no hardcoded default.
"""

from __future__ import annotations

import json
import logging
import re
import time
import threading
from datetime import datetime, timezone
from queue import Queue, Empty
from typing import Any, Callable

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.middleware.auth import AuthContext, reject_parent

from app.agents.conversation_agent import ConversationAgent
from app.agents.diagnosis_agent import DiagnosisAgent
from app.agents.multimodal_agent import MultimodalAgent
from app.config import settings
from app.db.engine import SessionLocal
from app.db.models import AnswerRecordModel, DailyTaskModel, LearnerModel, PracticeQuestionModel, ResourceModel, SessionModel
from app.db.repository import (
    get_bookmarked_ids,
    get_daily_tasks as repo_get_daily_tasks,
    get_daily_tasks_for_learner as repo_get_daily_tasks_for_learner,
    get_latest_learning_path as repo_get_latest_learning_path,
    get_learner,
    get_learner_aggregated_profile,
    get_learner_sessions,
    get_messages as repo_get_messages,
    get_or_create_session,
    list_sessions as repo_list_sessions,
    save_profile_snapshot,
    toggle_bookmark,
    update_task_completion as repo_update_task_completion,
    delete_session as repo_delete_session,
)
from app.services.agent_service import (
    get_analytics as ag_get_analytics,
    get_learning_path as ag_get_learning_path,
    get_profile as ag_get_profile,
    get_resources as ag_get_resources,
    run_agents as ag_run_agents,
)
from app.services.intent_router import get_agent_ids, should_run_agents, chat_only_intents
from app.schemas.feedback import FeedbackSignal
from app.utils.errors import InvalidEventTypeError, MissingSessionIdError, NotFoundError
from app.utils.profile_facts import apply_state_facts_to_result, profile_item
from app.utils.profile_normalizer import PROFILE_DIMENSION_LABELS, normalize_profile_dimensions
from app.services.profile_v2 import INTEREST_QUESTIONS, assess_interest, build_profile_v2, update_context as update_profile_v2_context, update_self_report
from app.services.conversation_state import conversation_store
from app.services.course_catalog import course_catalog
from app.services.learning_tracker import learning_tracker
from app.services.llm_client import get_llm_client
from app.schemas.product import ProductApiResponse

router = APIRouter(tags=["product"])


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _product_response(
    data: dict[str, Any],
    *,
    session_id: str = "",
    subject_id: str = "",
    message: str = "success",
    status: str = "success",
    source: str = "runtime_kit",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a unified response dict with consistent envelope fields."""
    return {
        "status": status,
        "data": data,
        "message": message,
        "warnings": warnings or [],
        "source": source,
        "sessionId": session_id,
        "subjectId": subject_id,
    }


def _validate_message(message: str) -> None:
    """Validate the *message* field for chat/agent-trigger endpoints.

    Raises:
        ValidationError: if message is empty or exceeds the length limit.
    """
    from app.utils.errors import ValidationError

    if not message or not message.strip():
        raise ValidationError(
            "消息内容不能为空",
            code="EMPTY_MESSAGE",
        )
    if len(message) > 10_000:
        raise ValidationError(
            f"消息内容过长（{len(message)}/{10_000} 字符）",
            code="MESSAGE_TOO_LONG",
        )


def _validate_subject_id(subject_id: str | None) -> None:
    """Validate that *subject_id* is non-empty when required.

    Raises:
        ValidationError: if subject_id is missing or empty.
    """
    from app.utils.errors import ValidationError

    if not subject_id or not str(subject_id).strip():
        raise ValidationError(
            "subjectId 不能为空",
            code="MISSING_SUBJECT_ID",
        )


def _get_bookmarks(session_id: str) -> set[str]:
    """Get bookmarked resource IDs from DB for a session."""
    try:
        db = SessionLocal()
        return get_bookmarked_ids(db, session_id)
    finally:
        db.close()


def _llm_client():
    return get_llm_client(settings.llm_provider)


def _intent_context(session_id: str | None = None) -> dict[str, Any]:
    if not session_id:
        return {}
    state = conversation_store.get(session_id)
    result = state.last_result or {}
    resources = result.get("resources") if isinstance(result, dict) else []
    learning_path = result.get("learning_path") if isinstance(result, dict) else []
    diagnosis = result.get("diagnosis") if isinstance(result, dict) else {}
    recent_messages = state.messages[-6:] if state.messages else []

    recent_resource_ids = []
    for item in resources or []:
        if isinstance(item, dict):
            resource_id = item.get("id") or item.get("resource_id")
            if resource_id:
                recent_resource_ids.append(str(resource_id))

    recent_weak_topics = []
    if isinstance(diagnosis, dict):
        for item in diagnosis.get("weak_topics") or diagnosis.get("weak_knowledge_points") or []:
            if isinstance(item, dict):
                topic = item.get("name") or item.get("topic") or item.get("title")
            else:
                topic = item
            if topic:
                recent_weak_topics.append(str(topic))

    recent_stage_id = None
    if isinstance(diagnosis, dict) and diagnosis.get("recommended_stage_id"):
        recent_stage_id = str(diagnosis.get("recommended_stage_id"))
    elif learning_path and isinstance(learning_path[0], dict):
        stage_id = learning_path[0].get("id") or learning_path[0].get("stage_id")
        recent_stage_id = str(stage_id) if stage_id else None

    return {
        "session_id": session_id,
        "subject_id": result.get("course_id") if isinstance(result, dict) else None,
        "subject_name": state.facts.get("target_course"),
        "last_intent": state.last_intent,
        "last_agent_result": result,
        "has_profile": bool(state.facts or (isinstance(result, dict) and result.get("profile"))),
        "has_learning_path": bool(learning_path),
        "has_resources": bool(resources),
        "has_diagnosis": bool(diagnosis),
        "recent_weak_topics": recent_weak_topics,
        "recent_resource_ids": recent_resource_ids,
        "recent_stage_id": recent_stage_id,
        "recent_messages": recent_messages,
        "feedback_signal": state.feedback_signal,
    }


def _classify_intent(message: str, session_id: str | None = None) -> dict[str, Any]:
    """用 ConversationAgent 进行对话理解，返回包含 reply 和 action 的结果。"""
    agent = ConversationAgent(mock_data={}, llm_client=_llm_client())
    context = _intent_context(session_id)
    context["user_message"] = message
    if "profile_facts" not in context:
        context["profile_facts"] = {}
    context["profile_facts"]["_raw_user_message"] = message

    # 加载对话历史 + last_proposal
    if session_id:
        state = conversation_store.get(session_id)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in state.messages[-20:]
        ]
        context["conversation_history"] = history
        context["last_proposal"] = state.last_proposal

    return agent.run(context)


def _public_intent_result(intent: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(intent, dict):
        return {}
    fields = (
        "intent",
        "primary_intent",
        "secondary_intents",
        "confidence",
        "should_run_agents",
        "should_run_full_workflow",
        "needs_subject",
        "needs_clarification",
        "clarification_question",
        "extracted",
        "reason",
        "source",
        "tasks",
        "constraints",
        "execution_plan",
        "decomposition_source",
        "decomposition_confidence",
    )
    result = {field: intent.get(field) for field in fields}
    # 也带上 ConversationAgent 的 reply 和 action
    if intent.get("reply"):
        result["reply"] = intent["reply"]
    if intent.get("action"):
        result["action"] = intent["action"]
    return result


def _run_agents(
    message: str,
    session_id: str,
    progress_callback: Callable | None = None,
    agents_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Trigger the multi-agent pipeline via AgentService and persist results.

    Args:
        agents_filter: 指定只运行哪些 Agent。None 表示全部。典型用法：
            - None / ["profile_agent","knowledge_agent","diagnosis_agent","planner_agent","resource_agent","review_agent"]
              → 全量生成
            - ["profile_agent","diagnosis_agent"] → 只诊断
            - ["profile_agent","planner_agent"] → 只规划
            - ["profile_agent","resource_agent"] → 只推荐资源
    """
    state = conversation_store.get(session_id)
    user_topic = state.facts.get("target_course") or message
    selected_course = course_catalog.match_course(user_topic)

    if selected_course is None:
        selected_course = {
            "course_id": f"custom_{abs(hash(user_topic)) % 10000:04d}",
            "course_name": user_topic.strip(),
            "description": f"用户自定义学习主题：{user_topic.strip()}",
            "chapters": [],
            "chapter_count": 0,
        }

    course_id = str(selected_course.get("course_id"))
    result = ag_run_agents(
        session_id=session_id,
        user_message=message,
        course_id=course_id,
        progress_callback=progress_callback,
        agents_filter=agents_filter,
    )
    if selected_course and "course" not in result:
        result["course"] = {
            "course_id": selected_course.get("course_id"),
            "course_name": selected_course.get("course_name"),
            "description": selected_course.get("description", ""),
            "chapter_count": selected_course.get("chapter_count", len(selected_course.get("chapters", []))),
        }
    apply_state_facts_to_result(result, state.facts, selected_course)
    return result


def _normalize_frontend_dimensions(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert DB-format dimensions (text value) to frontend-format (numeric score + description).

    DB format:  [{"key": "major_background", "label": "专业背景", "value": "软件工程大二", "confidence": 0.9}]
    Frontend:   [{"key": "major_background", "label": "专业背景", "value": 76, "confidence": 0.9, "description": "软件工程大二", "updatedAt": ...}]
    """
    result: list[dict[str, Any]] = []
    for dim in dimensions:
        if not isinstance(dim, dict):
            continue
        key = dim.get("key", "")
        text_value = str(dim.get("value", ""))
        score = int(dim.get("score", _dimension_score(key, dim)))
        explanation = str(dim.get("explanation", dim.get("description", text_value)))
        label = _DIMENSION_LABELS.get(key, dim.get("label", key))
        icon_map = {"专业背景":"BookOpen","知识基础":"Brain","学习目标":"Heart","认知风格":"Brain","易错模式":"AlertCircle","编程能力":"Code","学习进度":"Clock","兴趣方向":"Heart","学习节奏":"Clock"}
        result.append({
            "id": key,
            "key": key,
            "name": label,
            "label": label,
            "value": score,
            "score": score,
            "description": text_value or explanation,
            "explanation": explanation,
            "confidence": dim.get("confidence", 0.75),
            "evidence": str(dim.get("evidence", "")),
            "source": str(dim.get("source", "rule_based_fallback")),
            "icon": icon_map.get(label, "Brain"),
            "updatedAt": int(time.time() * 1000),
        })
    return result


def _dimension_score(key: str, item: dict[str, Any]) -> int:
    value = str(item.get("value", ""))
    base = int(float(item.get("confidence", 0.75)) * 80)
    if any(word in value for word in ["弱", "薄弱", "不会", "没学过", "一般"]):
        return max(35, base - 20)
    if any(word in value for word in ["较好", "熟悉", "掌握", "可以", "基础"]):
        return min(90, base + 10)
    if key == "error_patterns":
        return max(30, min(55, base - 25))  # error patterns are inherently lower-scoring
    if key in {"learning_goal", "interest_direction"}:
        return min(88, base + 8)
    if key == "learning_rhythm":
        return max(50, base)  # neutral default
    return max(50, min(85, base))


# 画像维度中文标签映射
_DIMENSION_LABELS: dict[str, str] = {
    "major_background": "专业背景",
    "knowledge_base": "知识基础",
    "learning_goal": "学习目标",
    "cognitive_style": "认知风格",
    "error_patterns": "易错模式",
    "coding_ability": "编程能力",
    "learning_progress": "学习进度",
    "interest_direction": "兴趣方向",
    "learning_rhythm": "学习节奏",
}


def _to_profile(result: dict[str, Any]) -> dict[str, Any]:
    """Convert raw orchestrator result to frontend-friendly profile dict."""
    raw_profile = result.get("profile") or {}
    if not isinstance(raw_profile, dict):
        raw_profile = {}
    dimensions = [
        {
            "key": key,
            "label": _DIMENSION_LABELS.get(key, item.get("label", key) if isinstance(item, dict) else key),
            "value": item.get("value", "") if isinstance(item, dict) else str(item),
            "score": int(item.get("score", _dimension_score(key, item))) if isinstance(item, dict) else 50,
            "confidence": item.get("confidence", 0.75) if isinstance(item, dict) else 0.5,
            "description": item.get("explanation", item.get("value", "")) if isinstance(item, dict) else str(item),
            "explanation": item.get("explanation", item.get("value", "")) if isinstance(item, dict) else str(item),
            "evidence": item.get("evidence", "") if isinstance(item, dict) else "",
            "source": item.get("source", "rule_based_fallback") if isinstance(item, dict) else "rule_based_fallback",
            "updatedAt": int(time.time() * 1000),
        }
        for key, item in raw_profile.items()
    ]

    weak_points = result.get("diagnosis", {}).get("weak_knowledge_points", [])
    weaknesses = [
        {
            "topic": point.get("name", "待补齐知识点"),
            "mastery": 42 if point.get("priority") == "high" else 58,
            "priority": 9 if point.get("priority") == "high" else 6,
            "source": point.get("source", ["diagnosis"]),
            "risk": point.get("risk", 0.7 if point.get("priority") == "high" else 0.4),
            "suggestedResources": [],
            "reason": point.get("reason", ""),
        }
        for point in weak_points
    ]

    # Look up learner info from DB if available
    learner_id = None
    nickname = "学习者"
    session_id = result.get("session_id", "")
    if session_id:
        try:
            db = SessionLocal()
            sess = db.get(SessionModel, session_id)
            if sess and sess.learner_id:
                learner = db.get(LearnerModel, sess.learner_id)
                if learner:
                    learner_id = learner.id
                    nickname = learner.nickname
        except Exception:
            logger.warning("Failed to look up learner info from session %s", session_id)
        finally:
            db.close()

    tracker_summary = learning_tracker.summary(result.get("session_id", ""))

    return {
        "id": result.get("session_id", ""),
        "learnerId": learner_id,
        "nickname": nickname,
        "createdAt": int(time.time() * 1000) - 86400000,
        "updatedAt": int(time.time() * 1000),
        "dimensions": dimensions,
        "weaknesses": weaknesses,
        "preferences": {
            "preferredFormats": ["text", "diagram", "code", "quiz"],
            "paceMinutes": 45,
            "difficulty": "beginner",
            "explainStyle": "diagram",
        },
        "history": {
            "totalStudyMinutes": tracker_summary.get("totalStudyMinutes", 0),
            "completedTopics": tracker_summary.get("completedTopics", []),
            "quizAccuracy": tracker_summary.get("quizAccuracy"),
            "streak": tracker_summary.get("streak", 0),
            "lastStudyDate": tracker_summary.get("lastStudyDate", 0),
        },
    }


# ── Resource type & source mapping ───────────────────────────────────

_TYPE_MAP: dict[str, str] = {"practice": "case_study", "multimodal": "video"}

_SOURCE_MAP: dict[str, str] = {
    "mock": "system_inferred",
    "agent": "agent_generated",
    "llm": "agent_generated",
    "llm_generated": "agent_generated",
    "inferred": "system_inferred",
    "model_inferred": "system_inferred",
    "fallback": "fallback",
    "": "system_inferred",
}


def _resource_type(resource_type: str) -> str:
    return _TYPE_MAP.get(resource_type, resource_type)


def _datetime_to_ms(value: str | None) -> int:
    if not value:
        return int(time.time() * 1000)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _source_label(source: str) -> str:
    """Map internal source labels to frontend-compatible labels."""
    if not source:
        return "system_inferred"
    if source in ("user_input", "agent_generated", "system_inferred", "fallback", "rule_based_fallback"):
        return source
    return _SOURCE_MAP.get(source, "system_inferred")


def _to_resource(
    item: dict[str, Any],
    course_id: str = "ai_intro",
    session_id: str = "",
) -> dict[str, Any]:
    content = item.get("content") or json.dumps(item.get("items", []), ensure_ascii=False, indent=2)
    resource_id = item.get("resource_id", "resource")
    bookmarks = _get_bookmarks(session_id)
    content_fmt = item.get("content_format", "markdown")
    related_stage_id = str(item.get("related_stage_id") or course_id)
    related_chapter = str(item.get("related_chapter") or "")
    related_chapter_id = str(item.get("related_chapter_id") or "")
    related_section_id = str(item.get("related_section_id") or "")
    related_knowledge_points = item.get("related_knowledge_points") or []
    quality_status = str(item.get("quality_status") or "passed")
    task_id = str(item.get("task_id") or "")
    return {
        "id": resource_id,
        "type": _resource_type(item.get("type", "lecture")),
        "title": item.get("title", "学习资源"),
        "description": item.get("description", ""),
        "content": content,
        "knowledgePoints": [related_stage_id] + (related_knowledge_points if isinstance(related_knowledge_points, list) else [related_knowledge_points]),
        "tags": [content_fmt, item.get("source", "agent_generated"), quality_status],
        "difficulty": item.get("difficulty", "easy"),
        "estimatedMinutes": item.get("estimatedMinutes", 20),
        "format": "diagram" if content_fmt == "mermaid" else ("code" if item.get("type") == "practice" else "text"),
        "mermaidDef": content if (content_fmt == "mermaid" or item.get("type") == "mindmap") else None,
        "codeBlocks": item.get("code_blocks"),
        "questions": item.get("items"),
        "pptOutline": item.get("ppt_outline"),
        "createdAt": int(time.time() * 1000),
        "bookmarked": resource_id in bookmarks,
        "studyStatus": item.get("studyStatus", "new"),
        "completedAt": item.get("completedAt") or item.get("completed_at"),
        "source": _source_label(item.get("source", "")),
        "relatedStageId": related_stage_id,
        "relatedChapterId": related_chapter_id,
        "relatedSectionId": related_section_id,
        "taskId": task_id,
        "relatedChapter": related_chapter,
        "relatedKnowledgePoints": related_knowledge_points if isinstance(related_knowledge_points, list) else [related_knowledge_points],
        "qualityStatus": quality_status,
        "sourceType": item.get("source_type", ""),
        "generationMode": item.get("generation_mode", ""),
        "reason": item.get("reason", ""),
        "evidence": item.get("evidence", []),
        "fallbackReason": item.get("fallback_reason", ""),
    }


def _stage_estimated_days(duration: Any) -> int:
    text = str(duration or "").strip()
    if not text:
        return 1

    hour_match = re.search(r"(\d+)\s*(?:小时|h|H)", text)
    if hour_match:
        return max(1, (int(hour_match.group(1)) + 23) // 24)

    range_match = re.search(r"(\d+)\s*(?:-|~|—|–|至|到)\s*(\d+)\s*(?:天|日)?", text)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        return max(1, abs(end - start) + 1)

    if re.search(r"第\s*\d+\s*(?:天|日)", text):
        return 1

    day_match = re.search(r"(\d+)\s*(?:天|日)", text)
    if day_match:
        return max(1, int(day_match.group(1)))

    return 1


def _raw_stages_to_nodes(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw orchestrator-format stages to frontend-format stages.

    Supports two formats:
    1. **Chapter-based** (new): stages → chapters → sections → knowledge_points
       With canonical IDs: path_xxx_s0, path_xxx_s0_ch0, etc.
    2. **Task-based** (legacy): stages with flat tasks → nodes
       Converts tasks into PathNode list.

    Detects format by checking for ``chapters`` key on the first stage.
    """
    if stages and isinstance(stages[0], dict) and stages[0].get("chapters"):
        return _chapter_stages_to_frontend(stages)
    return _task_stages_to_frontend(stages)


def _chapter_stages_to_frontend(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert chapter-structured stages to frontend format preserving hierarchy.

    Input: [{"stage_id": "path_xxx_s0", "title": "...", "order": 0,
             "chapters": [{"chapter_id": "...", "title": "...", "order": 0,
                           "sections": [{"section_id": "...", "title": "...",
                                         "knowledge_points": [{"kp_id": "...", ...}]}]}]}]
    Output: frontend LearningStage with chapters and nodes for backward compat.
    """
    result: list[dict[str, Any]] = []
    for stage_index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            continue
        chapters = _chapters_to_frontend(stage.get("chapters", []))
        # Build flat nodes for backward compat
        all_kps: list[dict[str, Any]] = []
        for ch in chapters:
            for sec in ch.get("sections", []):
                for kp in sec.get("knowledgePoints", []):
                    all_kps.append({
                        "id": kp["id"],
                        "topic": kp.get("name", ""),
                        "description": sec.get("goal", ""),
                        "prerequisites": [],
                        "mastery": kp.get("mastery", 0),
                        "status": _normalize_content_status(kp.get("status", "not_started")),
                        "resources": [],
                        "isKeyPoint": kp.get("type") == "concept",
                    })

        stage_days = max(1, sum(
            sec.get("estimatedMinutes", 45)
            for ch in chapters
            for sec in ch.get("sections", [])
        ) // 60)

        result.append({
            "id": stage.get("stage_id", f"stage_{stage_index}"),
            "order": stage.get("order", stage_index - 1) + 1,
            "title": stage.get("title", f"阶段 {stage_index}"),
            "description": stage.get("description", ""),
            "chapters": chapters,
            "nodes": all_kps,  # backward compat
            "objective": "",
            "estimatedDays": stage_days or 1,
            "tasks": [],
            "resourceTypes": [],
            "orderingReason": "",
        })
    return result


def _chapters_to_frontend(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert chapter dicts to frontend Chapter format."""
    result: list[dict[str, Any]] = []
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        sections: list[dict[str, Any]] = []
        for sec in ch.get("sections", []):
            kps: list[dict[str, Any]] = []
            for kp in sec.get("knowledge_points", []):
                kps.append({
                    "id": kp.get("kp_id", ""),
                    "name": kp.get("name", ""),
                    "type": kp.get("type", "concept"),
                    "description": kp.get("description", ""),
                    "mastery": kp.get("mastery", 0),
                    "status": _normalize_content_status(kp.get("status", "not_started")),
                })
            sections.append({
                "id": sec.get("section_id", ""),
                "title": sec.get("title", ""),
                "goal": sec.get("goal", ""),
                "estimatedMinutes": sec.get("estimated_minutes", 45),
                "status": _normalize_content_status(sec.get("status", "not_started")),
                "knowledgePoints": kps,
                "lectureIds": sec.get("lectureIds", []),
            })
        result.append({
            "id": ch.get("chapter_id", ""),
            "title": ch.get("title", ""),
            "order": ch.get("order", 0),
            "status": _normalize_content_status(ch.get("status", "not_started")),
            "sections": sections,
            "mindmapId": ch.get("mindmapId"),
        })
    return result


def _normalize_content_status(raw: str) -> str:
    """Normalize a status string to a valid ContentStatus value."""
    valid = {"not_started", "in_progress", "mastered", "needs_review", "blocked"}
    status = str(raw or "").strip().lower()
    # Map legacy values
    legacy_map = {
        "locked": "blocked",
        "available": "not_started",
        "completed": "mastered",
    }
    status = legacy_map.get(status, status)
    return status if status in valid else "not_started"


def _task_stages_to_frontend(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert legacy task-based stages to frontend format (existing behavior)."""
    result: list[dict[str, Any]] = []
    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            continue
        nodes = [
            {
                "id": f"{stage.get('stage_id', index)}_node_{node_index}",
                "topic": task,
                "description": stage.get("goal", ""),
                "prerequisites": [] if index == 1 else [f"stage_{index - 1}_node_1"],
                "mastery": 35 if index == 1 else 0,
                "status": "available" if index == 1 else "locked",
                "resources": [
                    {
                        "resourceId": f"res_{resource_type}_001",
                        "type": resource_type,
                        "title": resource_type,
                        "essential": node_index == 1,
                        "completed": False,
                    }
                    for resource_type in stage.get("resource_types", [])
                ],
                "isKeyPoint": node_index == 1,
            }
            for node_index, task in enumerate(stage.get("tasks", []), start=1)
        ]
        result.append({
            "id": stage.get("stage_id", f"stage_{index}"),
            "order": index,
            "title": stage.get("title", f"阶段 {index}"),
            "description": stage.get("duration", ""),
            "nodes": nodes,
            "chapters": [],
            "objective": stage.get("goal", ""),
            "estimatedDays": _stage_estimated_days(stage.get("duration", "")),
            "tasks": stage.get("tasks", []),
            "resourceTypes": stage.get("resource_types", []),
            "orderingReason": stage.get("reason", stage.get("ordering_reason", "")),
        })
    return result


def _estimated_path_days(stages: list[dict[str, Any]]) -> int:
    max_day = 0
    for stage in stages:
        duration = str(stage.get("duration", ""))
        for value in re.findall(r"\d+", duration):
            max_day = max(max_day, int(value))
    return max_day or 14


def _to_learning_path(result: dict[str, Any]) -> dict[str, Any]:
    course = result.get("course") or {}
    course_id = result.get("course_id", "custom")
    # 优先课程名 → 用户画像中的目标课程 → 不硬编码默认值
    state = conversation_store.get(result.get("session_id", ""))
    user_topic = state.facts.get("target_course", "") if state else ""
    course_name = (
        course.get("course_name")
        or user_topic
        or str(course_id)
    )
    raw_stages = result.get("learning_path", [])
    stages = _raw_stages_to_nodes(raw_stages)
    # computed fallback from stage durations
    fallback_days = _estimated_path_days(raw_stages)
    raw_est = result.get("estimatedDays")
    if isinstance(raw_est, int) and raw_est > 0:
        estimated_days = raw_est
    else:
        estimated_days = fallback_days

    return {
        "id": f"path_{course_id}",
        "title": f"{course_name}个性化学习路径",
        "description": result.get("diagnosis", {}).get("recommended_strategy", ""),
        "courseName": course_name,
        "stages": stages,
        "createdAt": int(time.time() * 1000),
        "overallProgress": result.get("overallProgress", 0),
        "estimatedDays": estimated_days,
        "source": "agent_generated",
    }


def _empty_profile(session_id: str) -> dict[str, Any]:
    """Return an empty profile structure when no data exists."""
    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    return {
        "id": session_id,
        "nickname": "学习者",
        "createdAt": 0,
        "updatedAt": 0,
        "dimensions": [],
        "weaknesses": [],
        "preferences": {
            "preferredFormats": [],
            "paceMinutes": 0,
            "difficulty": "unknown",
            "explainStyle": "unknown",
        },
        "history": {"totalStudyMinutes": 0, "completedTopics": [], "quizAccuracy": None, "streak": 0, "lastStudyDate": 0},
        "source": "none",
        "readiness": readiness,
    }


def _empty_learning_path(session_id: str) -> dict[str, Any]:
    """Return an empty learning path structure when no data exists."""
    return {
        "id": f"path_{session_id}",
        "title": "",
        "description": "",
        "courseName": "",
        "courseId": "",
        "stages": [],
        "createdAt": 0,
        "overallProgress": 0,
        "estimatedDays": 14,
        "source": "none",
    }

# ═══════════════════════════════════════════════════════════════════════
# Reply generators (chat logic)
# ═══════════════════════════════════════════════════════════════════════

_MULTIMODAL_PATTERNS = (
    "生成思维导图",
    "画个思维导图",
    "思维导图",
    "生成知识图谱",
    "画知识图",
    "知识图谱",
    "识别这张图片",
    "看看这张题图",
    "图片识别",
    "生成一张知识卡片",
    "知识卡片",
    "生成讲解图",
    "生成图片",
    "生成一个微课视频",
    "微课视频",
    "生成视频",
    "讲解视频",
)


_MULTIMODAL_PATTERNS = _MULTIMODAL_PATTERNS + (
    "\u751f\u6210\u601d\u7ef4\u5bfc\u56fe",
    "\u753b\u4e2a\u601d\u7ef4\u5bfc\u56fe",
    "\u601d\u7ef4\u5bfc\u56fe",
    "\u751f\u6210\u77e5\u8bc6\u56fe\u8c31",
    "\u753b\u77e5\u8bc6\u56fe",
    "\u77e5\u8bc6\u56fe\u8c31",
    "\u751f\u6210\u77e5\u8bc6\u5361\u7247",
    "\u77e5\u8bc6\u5361\u7247",
    "\u751f\u6210\u8bb2\u89e3\u56fe",
    "\u751f\u6210\u56fe\u7247",
    "\u751f\u6210\u4e00\u4e2a\u5fae\u8bfe\u89c6\u9891",
    "\u5fae\u8bfe\u89c6\u9891",
    "\u751f\u6210\u89c6\u9891",
    "\u8bb2\u89e3\u89c6\u9891",
    "\u56fe\u7247\u8bc6\u522b",
    "\u8fd9\u5f20\u56fe",
    "\u4e0a\u9762\u8fd9\u5f20\u56fe",
    "\u521a\u624d\u90a3\u5f20\u56fe",
    "\u8fd9\u5f20\u56fe\u7247",
    "\u56fe\u4e2d",
    "\u56fe\u7247\u91cc",
    "\u8fd9\u9053\u9898",
    "\u8fd9\u9875\u7b14\u8bb0",
    "\u9519\u9898\u56fe",
    "\u9898\u56fe",
    "\u7ee7\u7eed\u8bb2\u7b2c",
    "\u6839\u636e\u8fd9\u5f20\u56fe",
)


def _message_references_image(message: str) -> bool:
    text = str(message or "")
    if re.search(r"继续讲第\s*[0-9一二两三四五六七八九十]+\s*题", text):
        return True
    return any(pattern in text for pattern in (
        "这张图",
        "这张图片",
        "上面这张图",
        "刚才那张图",
        "图中",
        "图片里",
        "这道题",
        "这页笔记",
        "题图",
        "错题图",
    ))


def _is_multimodal_request(message: str, payload: dict[str, Any] | None = None) -> bool:
    if any(pattern in str(message or "") for pattern in _MULTIMODAL_PATTERNS):
        return True
    payload = payload or {}
    return bool(payload.get("attachments") or payload.get("image_url") or payload.get("image_base64"))


def _multimodal_image_input(payload: dict[str, Any]) -> dict[str, Any]:
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    return {
        "attachments": attachments,
        "image_url": str(payload.get("image_url") or ""),
        "image_base64": str(payload.get("image_base64") or ""),
    }


def _has_image_input(image_input: dict[str, Any]) -> bool:
    return bool(image_input.get("attachments") or image_input.get("image_url") or image_input.get("image_base64"))


def _reused_frontend_attachment(image_input: dict[str, Any]) -> bool:
    attachments = image_input.get("attachments")
    return bool(
        image_input.get("reused_from_last")
        or (isinstance(attachments, list) and attachments and isinstance(attachments[0], dict) and attachments[0].get("reused_from_last"))
    )


def _selected_image_attachment_id(image_input: dict[str, Any], cached_context: dict[str, Any] | None = None) -> str:
    attachments = image_input.get("attachments")
    if isinstance(attachments, list) and attachments and isinstance(attachments[0], dict):
        item = attachments[0]
        selected = item.get("file_id") or item.get("image_url") or item.get("url") or item.get("local_path") or ""
        if selected:
            return str(selected)
    selected = image_input.get("image_url") or ""
    if selected:
        return str(selected)
    cached = cached_context or {}
    uploaded = cached.get("last_uploaded_file")
    if isinstance(uploaded, dict):
        selected = uploaded.get("file_id") or uploaded.get("image_url") or uploaded.get("url") or uploaded.get("local_path") or ""
        if selected:
            return str(selected)
    last_input = cached.get("last_image_input")
    if isinstance(last_input, dict):
        return _selected_image_attachment_id(last_input)
    return ""


def _image_context_source(image_input: dict[str, Any], cached_context: dict[str, Any]) -> str:
    if _reused_frontend_attachment(image_input):
        return "last_uploaded_image"
    if _has_image_input(image_input):
        return "current_attachment"
    if cached_context.get("last_vision_result"):
        return "last_vision_result"
    if cached_context.get("last_image_input") or cached_context.get("last_uploaded_file"):
        return "last_uploaded_image"
    return "missing"


def _vision_from_multimodal_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("result") if isinstance(result.get("result"), dict) else {}
    vision = data.get("vision_result") if isinstance(data.get("vision_result"), dict) else {}
    if vision:
        return vision
    if any(data.get(key) for key in ("detected_text", "question_text", "summary", "possible_knowledge_points")):
        return data
    return {}


_BAD_MULTIMODAL_TEXT = (
    "see extracted_questions",
    "per-question answers",
    "extracted_questions",
    "raw_structured_result",
    "source_evidence",
)


def _bad_multimodal_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and any(marker in text for marker in _BAD_MULTIMODAL_TEXT)


def _clean_multimodal_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if _bad_multimodal_text(text) else text


def _questions_from_vision(vision: dict[str, Any]) -> list[dict[str, Any]]:
    raw = vision.get("extracted_questions") or vision.get("questions") or []
    if isinstance(raw, dict):
        raw = [raw]
    questions: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for idx, item in enumerate(raw, start=1):
            item = item if isinstance(item, dict) else {"question_text": str(item)}
            text = _clean_multimodal_text(
                item.get("question_text")
                or item.get("stem")
                or item.get("question")
                or item.get("text")
                or item.get("content")
                or item.get("title")
                or ""
            )
            try:
                question_index = int(item.get("index") or item.get("question_index") or idx)
            except (TypeError, ValueError):
                question_index = idx
            if not text:
                text = f"第 {question_index} 题题干识别不完整"
            questions.append({**item, "index": question_index, "question_text": text})
    fallback_question = _clean_multimodal_text(vision.get("question_text"))
    if not questions and fallback_question:
        questions.append({"index": 1, "question_text": fallback_question})
    return questions


def _cache_multimodal_context(session_id: str, image_input: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("status") != "completed":
        return
    data = result.get("result") if isinstance(result.get("result"), dict) else {}
    vision = _vision_from_multimodal_result(result)
    if not vision:
        return
    questions = data.get("extracted_questions") if isinstance(data.get("extracted_questions"), list) else _questions_from_vision(vision)
    attachments = image_input.get("attachments") if isinstance(image_input.get("attachments"), list) else []
    context: dict[str, Any] = {
        "last_vision_result": vision,
        "last_extracted_questions": questions,
        "last_multimodal_task_context": {
            "task_type": result.get("task_type"),
            "status": result.get("status"),
            "provider": result.get("provider"),
            "updated_at": int(time.time() * 1000),
        },
        "raw_structured_result": data,
    }
    if _has_image_input(image_input):
        context["last_image_input"] = image_input
    if attachments and isinstance(attachments[0], dict):
        context["last_uploaded_file"] = attachments[0]
    conversation_store.set_multimodal_context(session_id, context)


def _multimodal_learning_path(session_id: str) -> Any:
    state = conversation_store.get(session_id)
    cached = state.last_result or {}
    if isinstance(cached, dict) and cached.get("learning_path"):
        return cached.get("learning_path")
    try:
        stored = ag_get_learning_path(session_id)
    except Exception:
        stored = None
    if isinstance(stored, dict):
        return stored.get("stages") or stored.get("learning_path") or stored
    return stored


def _with_image_context_trace(trace: dict[str, Any], *, reused: bool, source: str, task_type: str, selected_image_attachment_id: str = "") -> dict[str, Any]:
    trace = dict(trace)
    trace["reused_image_context"] = reused
    trace["image_context_source"] = source
    trace["task_type"] = task_type
    if selected_image_attachment_id:
        trace["selected_image_attachment_id"] = selected_image_attachment_id
    return trace


def _multimodal_workflow_trace(
    result: dict[str, Any],
    *,
    reused_image_context: bool = False,
    image_context_source: str = "missing",
    selected_image_attachment_id: str = "",
) -> dict[str, Any]:
    task_type = str(result.get("task_type") or "")
    if isinstance(result.get("workflow_trace"), dict):
        return _with_image_context_trace(
            result["workflow_trace"],
            reused=reused_image_context,
            source=image_context_source,
            task_type=task_type,
            selected_image_attachment_id=selected_image_attachment_id,
        )
    status = str(result.get("status") or "generation_failed")
    workflow_status = "success" if status == "completed" else ("partial" if status == "provider_not_configured" else "failed")
    return _with_image_context_trace({
        "workflow_name": "multimodal_generation",
        "workflow_status": workflow_status,
        "pipeline_executed": True,
        "steps": [
            {
                "step": "multimodal",
                "agent": "MultimodalAgent",
                "status": status,
                "fallback_used": False,
                "summary": f"{result.get('task_type')} -> {status}",
                "output_keys": ["multimodal_result"] if result.get("result") else [],
            }
        ],
    }, reused=reused_image_context, source=image_context_source, task_type=task_type, selected_image_attachment_id=selected_image_attachment_id)


def _multimodal_reply(result: dict[str, Any]) -> str:
    task_type = result.get("task_type")
    status = result.get("status")
    error_code = result.get("error_code")
    raw_status = ((result.get("metadata") or {}).get("raw_status") if isinstance(result.get("metadata"), dict) else "")
    data = result.get("result") if isinstance(result.get("result"), dict) else {}
    for key in ("display_text", "teaching_text", "answer_text", "chat_text"):
        text = _clean_multimodal_text(data.get(key))
        if text:
            return text
    content = _clean_multimodal_text(result.get("content"))
    if content:
        return content
    if task_type == "image_understanding" and status == "completed":
        return "已完成图片理解，识别结果已整理成结构化信息。"
    if task_type == "image_to_mindmap" and status == "completed":
        return "已根据图片内容生成思维导图。"
    if task_type in {"image_to_flashcards", "note_image_to_flashcards", "question_image_to_flashcards"} and status == "completed":
        count = len(((result.get("result") or {}).get("cards")) or [])
        return f"已根据图片内容生成 {count} 张复习卡片。"
    if task_type in {"explain_image_question", "solve_image_question"} and status == "completed":
        return "已读取题图并整理讲解信息；证据不足的部分已标记为需要人工确认。"
    if task_type == "image_wrong_question_analysis" and status == "completed":
        return "已根据图片整理错题分析；证据不足的部分已标记为需要人工确认。"
    if task_type == "image_note_summary" and status == "completed":
        return "已根据图片整理笔记总结。"
    if task_type == "image_to_learning_plan" and status == "completed":
        return "已根据图片中的知识点整理学习计划。"
    if task_type == "image_to_variant_questions" and status == "completed":
        count = len(((result.get("result") or {}).get("variants")) or [])
        return f"已根据题图生成 {count} 道变式题；识别不确定处已标记。"
    if task_type == "image_to_resource_bundle" and status == "completed":
        return "已整理图片学习资源包，并生成待确认的资源保存候选和知识候选。"
    if task_type in {"video_generation", "micro_lesson_video", "video_script_generation"} and status == "provider_not_configured" and raw_status == "script_ready_provider_not_configured":
        return "视频模型尚未配置，但我已先生成微课脚本和分镜草稿，没有返回假视频链接。"
    if task_type in {"image_generation", "concept_card_generation", "teaching_diagram_generation"} and status == "completed":
        return "图片生成任务已返回结果。"
    if task_type == "mindmap_generation" and status == "completed":
        stage_count = ((result.get("result") or {}).get("stage_count")) or 0
        return f"已根据当前学习路径生成思维导图，共整理 {stage_count} 个阶段。"
    if error_code == "missing_input" and (str(task_type or "").startswith("image_") or task_type in {"explain_image_question", "solve_image_question"}):
        return "我还没有拿到可复用的图片。请先上传题图，或者在同一会话里接着上一张图继续提问。"
    if error_code == "missing_input":
        return "还缺少可执行这个多模态任务的输入。比如生成思维导图需要先有学习路径或知识内容。"
    if status == "provider_not_configured":
        return "这个多模态能力还没有配置对应的模型 Provider，所以我不会假装已经生成或识别成功。"
    if error_code == "unsupported":
        return "这个多模态请求暂时还不支持真实执行，我没有返回伪造结果。"
    return "多模态任务执行失败。"


def _multimodal_chat_payload(
    message: str,
    session_id: str,
    subject_id: str,
    payload: dict[str, Any],
    intent: dict[str, Any],
) -> dict[str, Any] | None:
    if not _is_multimodal_request(message, payload):
        return None

    state = conversation_store.get(session_id)
    image_input = _multimodal_image_input(payload)
    ignore_image_context = bool(payload.get("ignore_image_context"))
    references_image = _message_references_image(message)
    cached_context = {} if ignore_image_context else conversation_store.get_multimodal_context(session_id)
    original_has_image = _has_image_input(image_input) and not _reused_frontend_attachment(image_input)
    if not _has_image_input(image_input) and references_image:
        cached_input = cached_context.get("last_image_input") if isinstance(cached_context.get("last_image_input"), dict) else {}
        if cached_input and not cached_context.get("last_vision_result"):
            image_input = {
                "attachments": cached_input.get("attachments") or [],
                "image_url": cached_input.get("image_url") or "",
                "image_base64": cached_input.get("image_base64") or "",
                "reused_from_last": True,
            }
    image_context_source = _image_context_source(image_input if _has_image_input(image_input) else {}, cached_context)
    reused_image_context = (not original_has_image) and image_context_source in {"last_uploaded_image", "last_vision_result"}
    context_cache = cached_context if references_image or reused_image_context else {}
    context = {
        "session_id": session_id,
        "subject_id": subject_id,
        "user_message": message,
        "attachments": image_input.get("attachments") or [],
        "image_url": image_input.get("image_url") or "",
        "image_base64": image_input.get("image_base64") or "",
        "selected_image_attachment_id": _selected_image_attachment_id(image_input, cached_context),
        "learning_path": _multimodal_learning_path(session_id),
        "knowledge_context": (state.last_result or {}).get("knowledge_context", {}) if isinstance(state.last_result, dict) else {},
        "topic": state.facts.get("target_course") or subject_id,
        "subject_name": state.facts.get("target_course") or "",
        **context_cache,
    }
    result = MultimodalAgent().run(context)
    trace = _multimodal_workflow_trace(
        result,
        reused_image_context=reused_image_context,
        image_context_source=image_context_source,
        selected_image_attachment_id=_selected_image_attachment_id(image_input, cached_context),
    )
    trace["ignore_image_context"] = ignore_image_context
    trace["session_id"] = session_id
    _cache_multimodal_context(session_id, image_input, result)
    cached = state.last_result if isinstance(state.last_result, dict) else {}
    state.last_result = {**cached, "multimodal_result": result, "workflow_trace": trace}
    reply = _multimodal_reply(result)
    return {
        "sessionId": session_id,
        "reply": {
            "id": "assistant_msg_001",
            "role": "assistant",
            "content": reply,
            "timestamp": int(time.time() * 1000),
        },
        "intent_result": _public_intent_result(intent),
        "multimodal_result": result,
        "workflow_trace": trace,
    }


def _learning_plan_reply(result: dict[str, Any], intent: dict[str, Any]) -> str:
    path = _to_learning_path(result)
    stages = path.get("stages", [])
    metadata = result.get("planner_metadata") if isinstance(result.get("planner_metadata"), dict) else {}

    if not stages:
        reason = result.get("skip_reason") or result.get("overall_error") or "学习路径为空"
        return (
            "这次生成模块没有成功产出学习路径。"
            f"原因：{reason}。你可以稍后重试，或者先告诉我想学习的课程/方向。"
        )

    titles = [str(stage.get("title", "")).strip() for stage in stages if stage.get("title")]
    title_text = "、".join(titles[:5])
    days = metadata.get("estimated_days") or metadata.get("estimatedDays") or path.get("estimatedDays")
    rhythm = str((result.get("profile") or {}).get("learning_rhythm", {}).get("value", "")).strip()
    risk_flags = set(metadata.get("risk_flags") or [])
    priority_basis = set(metadata.get("priority_basis") or [])
    resources_count = len(result.get("resources") or [])

    notes: list[str] = []
    if "time_budget_tight" in risk_flags:
        notes.append("时间比较紧，我会优先安排重点突破。")
    elif "time_budget" in priority_basis:
        notes.append("我已按你提供的时间安排规划节奏。")
    if rhythm and rhythm not in {"学习节奏待补充", "暂未确定", "未提及"}:
        notes.append(f"时间安排参考：{rhythm}。")
    if resources_count:
        notes.append(f"已配套生成 {resources_count} 个学习资源。")

    note_text = "\n".join(f"- {note}" for note in notes)
    return (
        f"已按你的信息生成第一版学习方案：周期约 {days} 天，共 {len(stages)} 个阶段。\n\n"
        f"重点阶段包括：{title_text}。\n\n"
        f"{note_text}\n\n"
        "你可以到「学习路径」和「资源库」页面查看完整内容。"
    ).strip()


def _learning_subject(state) -> str:
    return str(state.facts.get("target_course") or "").strip()


def _ask_learning_subject_reply() -> str:
    return "可以。你想学习哪门课或哪个方向？告诉我学习对象后，我就能生成第一版学习方案。"


def _confirmation_clarification_reply() -> str:
    return "你是想让我开始生成学习方案，还是继续补充信息？"


def _is_bare_confirmation(message: str) -> bool:
    return re.sub(r"\s+", "", message.strip().lower()) in {
        "可以", "好", "好的", "行", "嗯", "嗯嗯", "ok", "yes", "就这样", "按这个来"
    }

def _casual_reply(session_id: str) -> str:
    """LLM 完全不可用时的最终兜底回复——极简、自然。"""
    if not session_id:
        raise ValueError("session_id is required for _casual_reply")
    state = conversation_store.get(session_id)
    if state.messages:
        return "还有什么想了解的？或者说说你最近学得怎么样？"
    return "你好！想学什么？之前有没有接触过相关内容？随便聊聊就好。"


def _date_query_reply() -> str:
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"今天是 {now.year} 年 {now.month} 月 {now.day} 日，{weekdays[now.weekday()]}。"


def _clarification_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    if not state.messages:
        return "没太理解你的意思，能换个方式再说说吗？"
    questions = conversation_store.next_questions(state, limit=2)
    if questions:
        return f"我的意思是先聊聊{'和'.join(questions[:2])}，了解清楚了我才好帮你规划。你觉得呢？"
    return "还有什么想了解的？或者你有具体的学习困惑也可以直接说。"


def _format_known_and_missing(session_id: str) -> tuple[str, list[dict[str, str]]]:
    state = conversation_store.get(session_id)
    known = "\n".join(conversation_store.known_lines(state))
    supplemental = "\n".join(conversation_store.supplemental_lines(state))
    if supplemental:
        known = f"{known}\n\n补充背景：\n{supplemental}" if known else f"补充背景：\n{supplemental}"
    missing = conversation_store.missing_fields(state, limit=4)
    return known, missing


def _readiness_line(session_id: str) -> str:
    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    return f"画像完整度：{readiness['filledCount']}/{readiness['totalCount']} 项"


def _info_request_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, missing = _format_known_and_missing(session_id)
    if not missing:
        return "信息差不多了！不过你还有什么特别想重点突破的方向吗？没有的话说「开始」我就给你出方案了。"
    questions = conversation_store.next_questions(state, limit=2)
    qs = "、".join(questions[:2]) if questions else "你的学习目标和时间安排"
    return f"收到。再跟我聊聊{qs}？了解越多我规划得越准。"


def _profile_query_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    if state.last_result is None:
        _, missing = _format_known_and_missing(session_id)
        if missing:
            qs = [m.get('question', '') for m in missing[:2]]
            return f"了解了一些，不过我还想知道{'和'.join(qs) if qs else '更多细节'}。能再聊聊吗？"
        return "跟我说说你想学什么、之前有没有基础？"

    profile = _to_profile(state.last_result)
    descriptions = [
        f"{dimension['label']}：{dimension['description']}"
        for dimension in profile["dimensions"] if dimension.get("description")
    ][:3]
    return "根据目前的信息，我觉得你" + "；".join(descriptions) + "。还有什么要补充的吗？没有的话说「开始」就行。"


def _profile_update_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, missing = _format_known_and_missing(session_id)
    updated = "\n".join(conversation_store.updated_lines(state))
    supplemental_updated = "\n".join(conversation_store.updated_supplemental_lines(state))
    conflicts = "\n".join(conversation_store.conflict_lines(state))
    update_text = "\n".join(part for part in [updated, supplemental_updated] if part) or "- 已记录你的补充信息"
    missing_questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=2))
    readiness = conversation_store.readiness(state)
    conflict_notice = f"\n\n检测到和之前画像不一致的信息，已按你最新说法更新：\n{conflicts}" if conflicts else ""

    if readiness["readyToPlan"]:
        return "收到，信息够了！还有什么特别想攻克的难点吗？没有的话说「开始生成」我就出方案。"
    if missing:
        q = conversation_store.next_questions(state, limit=2)
        next_q = "和".join(q[:2]) if q else "你的学习时间"
        return f"收到。再聊聊{next_q}？这样我规划得更贴合你的情况。"
    return "收到，记下了。还有别的吗？"


def _start_advice_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, _ = _format_known_and_missing(session_id)

    if not known and state.last_result is None:
        return "你还没告诉我具体情况呢。比如你是什么专业的？想学哪门课？基础怎么样？随便聊聊，像「我是软件大二，C还行，想一个月入门数据结构」这样就行。"

    if state.last_result:
        path = state.last_result.get("learning_path", [])
        first_stage = path[0] if path else {}
        first_task = (first_stage.get("tasks") or ["先阅读入门讲义"])[0]
        return f"建议从「{first_stage.get('title', '第一阶段')}」开始，先{first_task}，把概念框架搭起来再进练习。"

    target = state.facts.get("target_course", "目标课程")
    return f"建议先从「{target}」的基础概念开始，把前置知识理顺。说「开始生成」就能出完整路径。"


def _learning_plan_request_reply(
    message: str, intent: dict[str, Any], session_id: str,
    progress_callback: Callable | None = None,
) -> tuple[str, bool]:
    state = conversation_store.get(session_id)
    if not _learning_subject(state):
        return _ask_learning_subject_reply(), False

    try:
        result = _run_agents(message, session_id=session_id, progress_callback=progress_callback)
    except Exception as exc:
        logger.warning("Agent run failed during learning plan request for session %s", session_id)
        return f"生成模块暂时没有成功：{exc}。我没有假装已生成，你可以稍后重试。", False

    if result.get("pipeline_executed") is False:
        reason = result.get("skip_reason") or result.get("overall_error") or "pipeline 未执行"
        return f"生成模块这次没有真正执行成功，原因：{reason}。我没有假装已生成。", False
    return _learning_plan_reply(result, intent), bool(result.get("learning_path"))


def _tutoring_reply(message: str) -> str:
    return f"好问题！你说的「{message[:40]}」，能具体到哪个知识点吗？是概念不太清楚还是做题卡住了？跟我说说细节我好对症讲解。"


def _resource_request_reply(message: str, session_id: str, progress_callback: Callable | None = None) -> str:
    result = _run_agents(message, session_id=session_id, progress_callback=progress_callback)
    resources = [_to_resource(item, result.get("course_id", "ai_intro"), session_id) for item in result.get("resources", [])]
    names = "、".join(item["title"] for item in resources[:5])
    return (
        "我识别到你在请求学习资源。\n\n"
        f"当前已为你准备这些资源：{names}\n\n"
        "可以到「资源库」页面查看。后续 ResourceAgent 会进一步接入大模型，按主题实时生成讲义、题库、思维导图和实操案例。"
    )


def _diagnosis_context(message: str, session_id: str) -> dict[str, Any]:
    state = conversation_store.get(session_id)
    cached = state.last_result or {}

    try:
        stored_profile = ag_get_profile(session_id)
    except Exception:
        stored_profile = None
    try:
        stored_path = ag_get_learning_path(session_id)
    except Exception:
        stored_path = None
    try:
        stored_resources = ag_get_resources(session_id)
    except Exception:
        stored_resources = []
    try:
        analytics = ag_get_analytics(session_id)
    except Exception:
        analytics = {}

    profile = cached.get("profile") or ((stored_profile or {}).get("dimensions") or [])
    learning_path = cached.get("learning_path") or ((stored_path or {}).get("stages") or [])
    resources = cached.get("resources") or stored_resources or []

    return {
        "session_id": session_id,
        "user_message": message,
        "profile": profile,
        "profile_facts": dict(state.facts),
        "learning_path": learning_path,
        "resources": resources,
        "knowledge_context": cached.get("knowledge_context") or {},
        "analytics": analytics,
    }


def _run_diagnosis(message: str, session_id: str) -> dict[str, Any]:
    result = DiagnosisAgent(mock_data={}).run(_diagnosis_context(message, session_id))
    diagnosis = result["diagnosis"]
    conversation_store.set_diagnosis(session_id, diagnosis)
    return diagnosis


def _diagnosis_reply(message: str, session_id: str) -> str:
    diagnosis = _run_diagnosis(message, session_id)
    weak_topics = diagnosis.get("weak_topics") or []
    if weak_topics:
        topic_lines = "\n".join(
            f"- {item.get('topic', '待确认知识点')}（{item.get('priority', 'medium')}）：{item.get('reason', '')}"
            for item in weak_topics
        )
    else:
        topic_lines = "- 暂无足够证据确认具体薄弱点"

    action_lines = "\n".join(f"- {action}" for action in diagnosis.get("next_actions") or [])
    limitation_lines = "\n".join(f"- {item}" for item in diagnosis.get("limitations") or [])
    return (
        "学习诊断结果\n\n"
        f"{diagnosis.get('summary', '')}\n\n"
        f"薄弱点/待验证重点：\n{topic_lines}\n\n"
        f"下一步：\n{action_lines or '- 完成一次练习后重新诊断'}\n\n"
        f"诊断限制：\n{limitation_lines or '- 当前未发现额外限制'}\n\n"
        f"诊断来源：{diagnosis.get('source', 'rule_based_diagnosis')}；"
        f"置信度：{float(diagnosis.get('confidence', 0)):.0%}"
    )


def _looks_like_diagnosis_reply(reply: str) -> bool:
    return str(reply or "").lstrip().startswith("学习诊断结果")


def _feedback_reply(message: str, session_id: str) -> str:
    learning_tracker.log({"event": "chat_feedback", "metadata": {"message": message}}, session_id=session_id)
    return (
        "收到你的学习反馈了。我已经记录这次反馈，后续会用于调整画像、资源推荐和学习路径。\n\n"
        "学习事件已持久化保存。"
    )


# _unknown_reply 已删除 —— 设计文档 §6.1 明确禁止"请选择方向"式模板话术。
# 当 LLM 失败时，ConversationAgent._rule_fallback 返回 action + 空 reply，
# 由 _casual_reply 作为最终兜底。


def _reply_for_intent(
    message: str, intent: dict[str, Any], session_id: str,
    progress_callback: Callable | None = None,
) -> tuple[str, bool]:
    """统一回复入口。ConversationAgent 是唯一的总控。

    流程：
    1. ConversationAgent 已判断 action（intent 模式）
    2. action=none/unsafe → 直接返回 ConversationAgent 的自然语言回复
    3. action 需要执行 Agent → 调用 Orchestrator，然后 ConversationAgent
       final_reply 模式根据真实执行结果生成最终回复
    """
    # 用 ConversationAgent 返回的 facts 更新 conversation_store
    llm_facts = intent.get("facts", {})
    if llm_facts and session_id:
        state = conversation_store.get(session_id)
        fact_mapping = {
            "background": "background",
            "target_course": "target_course",
            "knowledge_base": "knowledge_base",
            "weak_points": "weak_points",
            "learning_goal": "learning_goal",
            "time_budget": "time_budget",
            "preference": "preference",
            # ── 补充映射 ──
            "daily_time": "time_budget",
            "exam_goal": "learning_goal",
            "study_period": "time_budget",
            "coding_level": "knowledge_base",
            "major": "background",
            "identity": "background",
            "academic_background": "background",
            "current_level": "knowledge_base",
            "cognitive_style": "preference",
            "learning_preference": "preference",
            "learning_rhythm": "time_budget",
            "interest_direction": "target_course",
            "weakness": "weak_points",
            "strengths": "knowledge_base",
        }
        for llm_key, fact_key in fact_mapping.items():
            value = str(llm_facts.get(llm_key, "")).strip()
            if value and len(value) >= 2:
                invalid = {"的是什么", "的是什么诶", "什么", "啥", "这个", "那个", "它", "他", "她", "未知", "未提及", "无", "none"}
                if value not in invalid:
                    state.facts[fact_key] = value
        # ── 未映射字段兜底存储 ──
        import json as _json
        extra_facts = {}
        for llm_key, value in llm_facts.items():
            if llm_key not in fact_mapping:
                val = str(value).strip()
                if val and len(val) >= 2:
                    invalid = {"的是什么", "什么", "啥", "未知", "未提及", "无", "none"}
                    if val not in invalid:
                        extra_facts[llm_key] = val
        if extra_facts:
            state.facts["_extra"] = _json.dumps(extra_facts, ensure_ascii=False)

    llm_reply = intent.get("reply", "")
    action = intent.get("action", "none")

    # ── 无上下文确认词追问 ──
    if intent.get("needs_clarification") and action == "none" and _is_bare_confirmation(message):
        return _confirmation_clarification_reply(), False

    # ── action=none：纯对话，不执行 Agent ──
    if action == "none":
        _detect_and_set_proposal(intent, session_id)
        return llm_reply or _casual_reply(session_id), False

    # ── 安全检查 ──
    if action == "unsafe":
        return llm_reply or "抱歉，我不能协助这类请求。如果你有学习相关的问题，我很乐意帮忙。", False

    # ── action 需要执行 Agent ──
    agent_actions = ("full_workflow", "diagnose", "plan", "resources", "profile", "knowledge", "generate_questions", "grade_answer")
    if action in agent_actions:
        # 硬条件检查：如果连学习对象都不知道，必须先问（§2.3）
        if action in ("full_workflow", "plan"):
            state = conversation_store.get(session_id)
            if not _learning_subject(state):
                return _ask_learning_subject_reply(), False

        # §4.1 + §11.1：支持逗号分隔的多 action
        actions = [a.strip() for a in action.split(",")]
        agents_filter = []
        for a in actions:
            af = get_agent_ids(a)
            if af is None:
                agents_filter = None
                break
            agents_filter.extend(af)
        if agents_filter is not None:
            agents_filter = list(dict.fromkeys(agents_filter))  # 去重
        logger.info("Scheduling agents for action=%s: %s", action, agents_filter)

        # 诊断模式：传入自适应标记和已有作答数据（M2）
        if action == "diagnose":
            state = conversation_store.get(session_id)
            previous_grades = []
            last_result = state.last_result or {}
            prev_grades = last_result.get("grading_results", [])
            if isinstance(prev_grades, list):
                previous_grades = prev_grades
            # 注入到 user_message 中，Orchestrator 会传给 DiagnosisAgent
            message_with_context = message
        else:
            message_with_context = message

        try:
            result = _run_agents(message_with_context, session_id=session_id,
                                 progress_callback=progress_callback,
                                 agents_filter=agents_filter)
        except Exception as exc:
            logger.warning("Agent run failed for session %s: %s", session_id, exc)
            return f"生成模块暂时没有成功：{exc}。我没有假装已生成，你可以稍后重试。", False

        if result.get("pipeline_executed") is False:
            skip_reason = result.get("skip_reason") or result.get("overall_error") or "pipeline 未执行"
            return f"生成流程这次没有完整执行（{skip_reason}）。你可以稍后重试。", False

        # 调用 ConversationAgent final_reply 模式生成最终回复
        final_reply = _generate_final_reply(message, session_id, result)

        # ── 主动推送：grading发现错误 → 建议重规划 + 存储 FeedbackSignal ──
        grading = result.get("grading_result", {}) or {}
        if grading.get("error_type") and grading["error_type"] != "null":
            et = grading.get("error_type", "")
            et_label = {"concept":"概念错误","calculation":"计算失误","misreading":"审题偏差","method":"方法不当","forgetting":"知识遗忘"}.get(et, et)
            final_reply += f"\n\n💡 检测到你在这道题上是**{et_label}**，可能需要调整学习计划重点强化这部分内容。要我现在帮你重新规划学习路径吗？"
            # 存储显式 FeedbackSignal（替代隐式 _pending_adjustment）
            signal = FeedbackSignal.from_grading_result(grading)
            state = conversation_store.get(session_id)
            state.feedback_signal = signal

        # 行动已完成，清除上次提议，检测是否提出了下一步
        conversation_store.set_proposal(session_id, None)
        _detect_and_set_proposal({"reply": final_reply}, session_id)
        return final_reply, bool(result.get("learning_path"))

    # 兜底
    return llm_reply or _casual_reply(session_id), False


# _agents_for_action removed — use get_agent_ids(action) from app.services.intent_router instead.


def _generate_final_reply(message: str, session_id: str, result: dict[str, Any]) -> str:
    """调用 ConversationAgent final_reply 模式，根据真实执行结果生成最终回复。"""
    from app.agents.conversation_agent import ConversationAgent
    import logging as _logging
    _log = _logging.getLogger(__name__)

    agent = ConversationAgent(mock_data={}, llm_client=_llm_client())
    state = conversation_store.get(session_id)
    stages = result.get("learning_path", [])
    resources = result.get("resources", [])
    diagnosis = result.get("diagnosis", {})

    context = {
        "mode": "final_reply",
        "user_message": message,
        "profile_facts": {"_raw_user_message": message},
        "conversation_history": [
            {"role": m["role"], "content": m["content"]}
            for m in state.messages[-20:]
        ],
        "pipeline_result": {
            "pipeline_executed": bool(result.get("pipeline_executed")),
            "agents_run": result.get("agents_run", []),
            "learning_path_created": bool(stages),
            "stage_count": len(stages),
            "stage_titles": [
                str(s.get("title", ""))
                for s in stages[:8]
                if isinstance(s, dict) and s.get("title")
            ],
            # ── 新增：阶段描述摘要（含目标和时长）──
            "stage_summaries": [
                {
                    "title": s.get("title", ""),
                    "goal": s.get("goal", ""),
                    "duration": s.get("duration", ""),
                }
                for s in stages[:5] if isinstance(s, dict)
            ],
            "resources_created": bool(resources),
            "resource_count": len(resources),
            # ── 新增：资源类型分布 ──
            "resource_types": list(set(
                r.get("type", "") for r in resources[:20]
                if isinstance(r, dict) and r.get("type")
            )),
            # ── 新增：诊断关键发现 ──
            "diagnosis_key_finding": str(
                diagnosis.get("diagnosis_summary", "")
            )[:100] if isinstance(diagnosis, dict) else "",
            "diagnosis_created": bool(diagnosis and diagnosis.get("weak_knowledge_points")),
            "estimated_days": result.get("estimatedDays"),
            "planner_metadata": result.get("planner_metadata"),
            "skip_reason": result.get("skip_reason", ""),
            "fallback_used": result.get("fallback_used", False),
        },
    }

    try:
        final_result = agent.run(context)
        reply = final_result.get("reply", "")
        if reply:
            return reply
    except Exception as exc:
        _log.warning("ConversationAgent final_reply failed: %s", exc)

    # LLM 失败 → 极简事实兜底（包含阶段标题以提供足够信息）
    parts = []
    if stages:
        titles = [str(s.get("title", "")) for s in stages[:5] if isinstance(s, dict) and s.get("title")]
        title_text = " → ".join(titles) if titles else f"{len(stages)} 个阶段"
        estimated = result.get("estimatedDays")
        if estimated:
            parts.append(f"已生成 {len(stages)} 个阶段（约{estimated}天）的学习方案：{title_text}")
        else:
            parts.append(f"已生成 {len(stages)} 个阶段的学习方案：{title_text}")
    if resources:
        parts.append(f"配套 {len(resources)} 个学习资源")
    if diagnosis and diagnosis.get("weak_knowledge_points"):
        parts.append("已完成诊断分析")
    if not parts:
        reply = "生成流程已完成。你可以到学习路径和资源库页面查看详细内容。"
    else:
        reply = "、".join(parts) + "。你可以到对应页面查看详细内容。"
    return reply


def _detect_and_set_proposal(intent: dict, session_id: str) -> None:
    if not session_id:
        return
    # 1. 标签优先
    llm_proposal = intent.get("_llm_proposal", "")
    if llm_proposal in {"plan","resources","questions","diagnose"}:
        conversation_store.set_proposal(session_id, llm_proposal)
        return
    # 2. 关键词检测 LLM 是否在提问（代码兜底，不依赖 LLM 标签）
    reply_lower = (intent.get("reply","") or "").lower()
    if any(w in reply_lower for w in ["生成路径","规划路径","开始规划","生成学习路径","要开始","要生成","要规划"]):
        conversation_store.set_proposal(session_id, "plan")
    elif any(w in reply_lower for w in ["配套资源","生成资源","配资源","学习资源","要配资源","整理资源"]):
        conversation_store.set_proposal(session_id, "resources")
    elif any(w in reply_lower for w in ["出题","练习题","巩固","要练习","做题"]):
        conversation_store.set_proposal(session_id, "questions")
    else:
        conversation_store.set_proposal(session_id, None)

def _will_run_agents(intent: dict[str, Any], session_id: str) -> bool:
    """Check whether the given intent will trigger agent execution."""
    action = intent.get("action", "")
    return action in ("diagnose", "plan", "resources", "full_workflow", "knowledge", "profile", "generate_questions", "grade_answer")


GEN_STAGES = [
    ("understanding", "正在理解需求", 5),
    ("profiling",    "正在生成画像", 25),
    ("planning",     "正在规划路径", 50),
    ("generating",   "正在生成资源", 75),
    ("saving",       "正在保存结果", 95),
]





@router.post("/chat/sessions")
def create_chat_session(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an empty chat session before its first message is sent."""
    session_id = _payload_session_id(payload)
    subject_id = _payload_subject_id(payload)
    learner_id = str(payload.get("learnerId", "")).strip() or None
    try:
        db = SessionLocal()
        session = get_or_create_session(db, session_id, learner_id=learner_id, subject_id=subject_id)
        conversation_store.get(session.id)
        return _product_response(
            {
                "sessionId": session.id,
                "title": session.title or "新对话",
                "createdAt": int(session.created_at.timestamp() * 1000) if session.created_at else int(time.time() * 1000),
            },
            session_id=session.id,
            subject_id=subject_id,
            source="db",
        )
    finally:
        db.close()


@router.get("/chat/sessions")
def list_sessions(subjectId: str = "", learnerId: str = "") -> dict[str, Any]:
    """List sessions, optionally filtered by subject and/or learner.

    Without filters, returns sessions for the default learner to avoid
    leaking all sessions from all users.
    """
    try:
        db = SessionLocal()
        # Resolve learner — default to the most recent learner if none specified
        resolved_learner_id: str | None = str(learnerId).strip() or None
        resolved_subject_id: str | None = str(subjectId).strip() or None
        if not resolved_learner_id and not resolved_subject_id:
            # No filters at all — scope to the single (most recent) learner
            from app.db.repository import get_or_create_learner
            default_learner = get_or_create_learner(db)
            resolved_learner_id = default_learner.id

        sessions = repo_list_sessions(
            db,
            learner_id=resolved_learner_id,
            subject_id=resolved_subject_id,
        )
        return _product_response(
            {"sessions": [
                {
                    "id": sess.id,
                    "title": sess.title,
                    "status": sess.status,
                    "subjectId": sess.subject_id or "",
                    "createdAt": int(sess.created_at.timestamp() * 1000) if sess.created_at else 0,
                    "updatedAt": int(sess.updated_at.timestamp() * 1000) if sess.updated_at else 0,
                }
                for sess in sessions
            ]},
            source="db",
        )
    finally:
        db.close()


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str) -> dict[str, Any]:
    try:
        db = SessionLocal()
        messages = repo_get_messages(db, session_id)
        return _product_response(
            {
                "sessionId": session_id,
                "messages": [
                    {
                        "id": f"msg_{msg.id}",
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": int(msg.created_at.timestamp() * 1000) if msg.created_at else 0,
                    }
                    for msg in messages
                ],
            },
            session_id=session_id, source="db",
        )
    finally:
        db.close()


@router.get("/chat/recover")
def recover_chat(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Return the latest assistant reply for recovery after interrupted generation.

    Called by the frontend when it detects an orphaned streaming message
    (user navigated away mid-generation).  Since Step 3.1 of the fix
    persists the reply inside _agent_worker, the conversation_store
    already holds the completed text even when the SSE generator was
    interrupted.
    """
    session_id = _resolve_session_id(sessionId, subjectId)
    state = conversation_store.get(session_id)
    generating = getattr(state, 'generating', False)
    current_progress = getattr(state, 'current_progress', None)
    assistant_msgs = [m for m in state.messages if m["role"] == "assistant"]
    if assistant_msgs:
        last = assistant_msgs[-1]
        return _product_response(
            {
                "sessionId": session_id,
                "reply": {
                    "id": f"msg_{int(time.time() * 1000)}",
                    "role": "assistant",
                    "content": last["content"],
                    "timestamp": last.get("timestamp", int(time.time() * 1000)),
                },
                "generating": generating,
                "currentProgress": current_progress,
            },
            session_id=session_id, source="store",
        )
    return _product_response(
        {"sessionId": session_id, "reply": None, "generating": generating, "currentProgress": current_progress},
        session_id=session_id, source="store",
    )


@router.post("/chat/sessions/{session_id}/reset")
def reset_session(session_id: str) -> dict[str, Any]:
    conversation_store.reset(session_id)
    return _product_response({"ok": True}, session_id=session_id, source="system")


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str) -> dict[str, Any]:
    """Delete a chat session and its associated data."""
    try:
        db = SessionLocal()
        ok = repo_delete_session(db, session_id)
        if not ok:
            return _product_response(
                None, message="会话不存在", source="db",
                session_id=session_id, status="error",
            )
        return _product_response(
            {"ok": True}, session_id=session_id, source="db",
        )
    finally:
        db.close()


@router.get("/chat/quick-commands")
def quick_commands(sessionId: str = "") -> dict[str, Any]:
    """Return quick-command suggestions personalised to the current session."""
    session_id = str(sessionId).strip() if sessionId else ""
    course_name = ""
    if session_id:
        try:
            state = conversation_store.get(session_id)
            course_name = str(state.facts.get("target_course", "")).strip()
        except Exception:
            pass
    if not course_name:
        try:
            for course in course_catalog.list_courses()[:1]:
                course_name = course.get("course_name", "")
        except Exception:
            pass
    subject = course_name or "这门课"
    commands = [
        {"id": "profile", "label": "了解我的基础", "icon": "User",
         "prompt": f"我想学{subject}，帮我了解一下我的基础" if course_name else "我想开始学习，帮我了解一下我的基础"},
        {"id": "plan", "label": "规划学习路径", "icon": "Map",
         "prompt": f"帮我规划{subject}的学习路径" if course_name else "帮我规划学习路径"},
        {"id": "diagnose", "label": "诊断薄弱点", "icon": "Activity",
         "prompt": f"帮我诊断一下在{subject}方面的薄弱点" if course_name else "帮我诊断一下薄弱点"},
        {"id": "questions", "label": "生成练习题", "icon": "Edit3",
         "prompt": f"根据我的学习情况，出几道{subject}的练习题" if course_name else "根据我的学习情况，出几道练习题"},
        {"id": "mindmap", "label": "生成思维导图", "icon": "Share2",
         "prompt": f"帮我生成{subject}的知识思维导图" if course_name else "帮我生成知识思维导图"},
        {"id": "explain", "label": "讲解知识点", "icon": "HelpCircle",
         "prompt": f"帮我详细讲解{subject}的一个知识点" if course_name else "帮我详细讲解一个知识点"},
    ]
    return _product_response(
        {"commands": commands, "courseName": course_name or None},
        source="profile" if course_name else "catalog",
    )

@router.get("/chat/agents")
def list_agents() -> dict[str, Any]:
    """Return the available agents with their names, icons, and descriptions.

    Used by the frontend chat sidebar to show the agent pipeline status instead
    of hardcoded agent names.
    """
    agents = [
        {
            "id": "profile_agent",
            "name": "画像分析",
            "icon": "🧠",
            "description": "分析学习背景、知识基础和偏好，构建多维学习画像",
            "stage": "profiling",
        },
        {
            "id": "knowledge_agent",
            "name": "知识检索",
            "icon": "📚",
            "description": "从课程知识库中检索相关知识点和前置概念",
            "stage": "profiling",
        },
        {
            "id": "diagnosis_agent",
            "name": "诊断分析",
            "icon": "🎯",
            "description": "基于画像和能力表现诊断薄弱环节和知识缺口",
            "stage": "profiling",
        },
        {
            "id": "planner_agent",
            "name": "路径规划",
            "icon": "📊",
            "description": "根据诊断结果和课程结构规划个性化学习阶段",
            "stage": "planning",
        },
        {
            "id": "resource_agent",
            "name": "资源生成",
            "icon": "📝",
            "description": "按学习路径生成讲义、思维导图、练习题等资源",
            "stage": "generating",
        },
        {
            "id": "review_agent",
            "name": "质量审查",
            "icon": "✅",
            "description": "审查生成资源的知识准确性、难度匹配度和完整性",
            "stage": "generating",
        },
    ]
    return _product_response({"agents": agents}, source="system")


@router.get("/chat/progress/{task_id}")
def generation_progress(task_id: str) -> dict[str, Any]:
    return _product_response(
        {"progress": {"stage": "多智能体生成中", "progress": 100, "agentName": "EduAgent", "detail": task_id}},
        source="mock",
    )

    
# ═══════════════════════════════════════════════════════════════════════
# Profile endpoints — read from DB, trigger via POST
# ═══════════════════════════════════════════════════════════════════════

def _profile_v2(session_id: str, legacy: dict[str, Any] | None = None) -> dict[str, Any]:
    state = conversation_store.get(session_id)
    legacy = legacy or ag_get_profile(session_id) or {}
    prefs = legacy.get("preferences") if isinstance(legacy.get("preferences"), dict) else {}
    course = course_catalog.match_course(str(state.facts.get("target_course") or ""))
    return build_profile_v2(
        dimensions=legacy.get("dimensions") if isinstance(legacy.get("dimensions"), list) else [],
        facts=state.facts,
        course=course,
        weaknesses=legacy.get("weaknesses") if isinstance(legacy.get("weaknesses"), list) else [],
        existing=prefs.get("profile_v2") if isinstance(prefs, dict) else None,
    )


def _save_profile_v2(session_id: str, profile_v2: dict[str, Any]) -> None:
    legacy = ag_get_profile(session_id) or {}
    prefs = dict(legacy.get("preferences") or {})
    prefs["profile_v2"] = profile_v2
    db = SessionLocal()
    try:
        save_profile_snapshot(
            db,
            session_id,
            dimensions=legacy.get("dimensions") if isinstance(legacy.get("dimensions"), list) else [],
            weaknesses=legacy.get("weaknesses") if isinstance(legacy.get("weaknesses"), list) else [],
            preferences=prefs,
            readiness_score=legacy.get("readiness_score"),
        )
    finally:
        db.close()


def _require_session_id(value: Any) -> str:
    session_id = str(value or "").strip()
    if not session_id:
        raise MissingSessionIdError()
    return session_id


def _resolve_session_id(sessionId: str = "", subjectId: str = "") -> str:
    # subjectId remains course context only; it must never identify a session.
    return _require_session_id(sessionId)


def _payload_session_id(payload: dict[str, Any]) -> str:
    return _require_session_id(payload.get("sessionId"))


def _payload_subject_id(payload: dict[str, Any]) -> str:
    """Extract optional subjectId from a JSON payload body."""
    return str(payload.get("subjectId", "")).strip()


def _ensure_session_linked(
    session_id: str,
    subject_id: str = "",
    learner_id: str | None = None,
) -> None:
    """Ensure the session row in DB is linked to the given subject and learner.

    Creates or updates the session row as a side effect so that subsequent
    ``list_sessions`` and analytics queries can filter by subject/learner.

    Handles race conditions gracefully: if a concurrent request already created
    the session, we fall back to an update instead of failing.
    """
    if not subject_id and not learner_id:
        return
    try:
        from sqlalchemy.exc import IntegrityError

        db = SessionLocal()
        sess = db.get(SessionModel, session_id)

        if sess is not None:
            changed = False
            if learner_id and not sess.learner_id:
                sess.learner_id = learner_id
                changed = True
            if subject_id and not sess.subject_id:
                sess.subject_id = subject_id
                changed = True
            if changed:
                db.commit()
            return

        # Session doesn't exist yet — try to create it
        from app.db.repository import get_or_create_learner
        learner = get_or_create_learner(db, learner_id)
        sess = SessionModel(
            id=session_id,
            learner_id=learner.id,
            subject_id=subject_id or None,
        )
        db.add(sess)
        try:
            db.commit()
        except IntegrityError:
            # Race condition: another request created it first
            db.rollback()
            sess = db.get(SessionModel, session_id)
            if sess is not None:
                changed = False
                if learner_id and not sess.learner_id:
                    sess.learner_id = learner_id
                    changed = True
                if subject_id and not sess.subject_id:
                    sess.subject_id = subject_id
                    changed = True
                if changed:
                    db.commit()
    except Exception:
        logger.warning("Failed to link session %s to subject/learner", session_id, exc_info=True)
    finally:
        db.close()


@router.get("/profile")
def get_profile(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Read the latest profile from the database. Never triggers agents."""
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    # Default preferences (safe for frontend)
    _default_prefs = {"preferredFormats": ["text"], "paceMinutes": 45, "difficulty": "beginner", "explainStyle": "text"}

    # Try DB first
    db_profile = ag_get_profile(session_id)
    if db_profile:
        state = conversation_store.get(session_id)
        readiness = conversation_store.readiness(state)
        db_prefs = db_profile.get("preferences") or {}

        # Look up learner info
        learner_id = None
        nickname = "学习者"
        try:
            db = SessionLocal()
            sess = db.get(SessionModel, session_id)
            if sess and sess.learner_id:
                learner = db.get(LearnerModel, sess.learner_id)
                if learner:
                    learner_id = learner.id
                    nickname = learner.nickname
        except Exception:
            logger.warning("Failed to look up learner for session %s in get_profile", session_id)
        finally:
            db.close()

        dims = _normalize_frontend_dimensions(db_profile.get("dimensions", []))
        bg = next((d for d in dims if d["key"] == "major_background"), None)
        goal_dim = next((d for d in dims if d["key"] == "learning_goal"), None)
        learning_goals = [goal_dim["description"]] if goal_dim and goal_dim.get("description") else []
        total_minutes = db_profile.get("history", {}).get("totalStudyMinutes", 0) if isinstance(db_profile.get("history"), dict) else 0
        completed = db_profile.get("history", {}).get("completedTopics", []) if isinstance(db_profile.get("history"), dict) else []

        return _product_response(
            {"profile": {
                "id": session_id,
                "learnerId": learner_id,
                "name": nickname,
                "nickname": nickname,
                "major": bg["description"] if bg else "未知专业",
                "grade": "大三" if bg and "大三" in str(bg.get("description","")) else "—",
                "lastActive": "刚刚",
                "totalStudyHours": round(total_minutes / 60),
                "completedCourses": len(completed) if isinstance(completed, list) else 0,
                "learningGoals": learning_goals,
                "dimensions": dims,
                "weaknesses": db_profile.get("weaknesses", []),
                "preferences": {**_default_prefs, **db_prefs},
                "history": {"totalStudyMinutes": total_minutes, "completedTopics": completed if isinstance(completed, list) else [], "quizAccuracy": None, "streak": 0, "lastStudyDate": 0},
                "createdAt": int(time.time() * 1000) - 86400000,
                "updatedAt": int(time.time() * 1000),
                "source": "db",
                "readiness": readiness,
            }, "profileV2": _profile_v2(session_id, {"dimensions": dims, "weaknesses": db_profile.get("weaknesses", []), "preferences": {**_default_prefs, **db_prefs}})},
            session_id=session_id, subject_id=subjectId, source="db",
        )

    # Fall back to in-memory last_result if available (transitional)
    state = conversation_store.get(session_id)
    if state.last_result:
        profile = _to_profile(state.last_result)
        readiness = conversation_store.readiness(state)
        profile["source"] = "agent_generated"
        profile["readiness"] = readiness
        return _product_response({"profile": profile, "profileV2": state.last_result.get("profile_v2") or _profile_v2(session_id, profile)}, session_id=session_id, subject_id=subjectId, source="agent")

    # No data at all — return empty structure
    empty = _empty_profile(session_id)
    return _product_response({"profile": empty, "profileV2": _profile_v2(session_id, empty)}, session_id=session_id, subject_id=subjectId, source="none")


@router.post("/profile/build")
def build_profile(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    """Trigger agent pipeline and build/refresh the student profile."""
    session_id = _payload_session_id(payload)
    subject_id = _payload_subject_id(payload)
    _ensure_session_linked(session_id, subject_id=subject_id)
    message = str(payload.get("message", "我想学习人工智能导论"))

    conversation_store.append_message(session_id, "user", message)
    result = _run_agents(message, session_id=session_id)
    profile = _to_profile(result)
    profile["source"] = "agent_generated"

    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    profile["readiness"] = readiness

    return _product_response({"profile": profile, "profileV2": result.get("profile_v2") or _profile_v2(session_id, profile)}, session_id=session_id, source="agent")


@router.patch("/profile/v2/context")
def update_profile_context(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    updates = payload.get("context")
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="context required")
    profile_v2 = update_profile_v2_context(_profile_v2(session_id), updates)
    _save_profile_v2(session_id, profile_v2)
    return _product_response({"profileV2": profile_v2}, session_id=session_id, source="user_input")


@router.patch("/profile/v2/self-report")
def update_profile_self_report(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    updates = payload.get("selfReport")
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="selfReport required")
    profile_v2 = update_self_report(_profile_v2(session_id), updates)
    _save_profile_v2(session_id, profile_v2)
    return _product_response({"profileV2": profile_v2}, session_id=session_id, source="user_input")


@router.post("/profile/v2/assess/interest")
def assess_profile_interest(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    answers = payload.get("answers")
    if not isinstance(answers, list):
        return _product_response({"questions": INTEREST_QUESTIONS}, session_id=session_id, source="rule_based")
    profile_v2 = assess_interest(_profile_v2(session_id), answers)
    _save_profile_v2(session_id, profile_v2)
    return _product_response({"profileV2": profile_v2, "questions": INTEREST_QUESTIONS}, session_id=session_id, source="rule_based")


@router.patch("/profile")
def update_profile(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    """Update profile fields directly (client-side edits). Persists to DB and syncs facts."""
    session_id = _payload_session_id(payload)
    state = conversation_store.get(session_id)

    # Use existing data as base, merge payload
    if state.last_result:
        profile = _to_profile(state.last_result)
    else:
        profile = _empty_profile(session_id)

    profile.update({k: v for k, v in payload.items() if k not in {"sessionId", "subjectId", "code", "message", "data"}})

    # Sync dimension updates back to conversation facts
    updated_dimensions = payload.get("dimensions")
    if isinstance(updated_dimensions, list):
        _DIM_TO_FACT: dict[str, str] = {
            "major_background": "background",
            "knowledge_base": "knowledge_base",
            "learning_goal": "learning_goal",
            "cognitive_style": "preference",
            "error_patterns": "weak_points",
            "interest_direction": "target_course",
            "learning_rhythm": "time_budget",
        }
        for dim in updated_dimensions:
            if not isinstance(dim, dict):
                continue
            dim_key = dim.get("key", "")
            if dim_key == "coding_ability":
                raise HTTPException(status_code=400, detail="能力维度不能直接编辑，请通过练习或诊断更新")
            fact_key = _DIM_TO_FACT.get(dim_key)
            if fact_key:
                dim_value = str(dim.get("value", dim.get("description", ""))).strip()
                if dim_value:
                    state.facts[fact_key] = dim_value

    # Persist updated profile to DB
    try:
        db = SessionLocal()
        profile_dimensions = profile.get("dimensions", [])
        dimensions_list = [
            {
                "key": dim.get("key", ""),
                "label": dim.get("label", dim.get("key", "")),
                "value": str(dim.get("value", dim.get("description", ""))),
                "score": dim.get("score", 50),
                "confidence": dim.get("confidence", 0.75),
                "explanation": dim.get("explanation", dim.get("description", "")),
                "evidence": str(dim.get("evidence", "")),
                "source": str(dim.get("source", "user_input")),
            }
            for dim in profile_dimensions
            if isinstance(dim, dict)
        ]
        readiness = conversation_store.readiness(state)
        save_profile_snapshot(
            db,
            session_id,
            dimensions=dimensions_list,
            weaknesses=profile.get("weaknesses"),
            preferences=profile.get("preferences"),
            readiness_score=readiness.get("score", 0),
        )
    finally:
        db.close()

    # Update in-memory last_result to stay consistent with DB
    if state.last_result and "profile" in state.last_result:
        for dim in profile_dimensions:
            if not isinstance(dim, dict):
                continue
            key = dim.get("key", "")
            if key in state.last_result.get("profile", {}):
                existing = state.last_result["profile"][key]
                if isinstance(existing, dict):
                    existing["value"] = dim.get("value", dim.get("description", ""))
                    existing["source"] = "user_input"
                    existing["confidence"] = 1.0

    return _product_response({"profile": profile}, session_id=session_id, source="user_input")


# ═══════════════════════════════════════════════════════════════════════
# Learner endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/learner/{learner_id}")
def get_learner_endpoint(learner_id: str) -> dict[str, Any]:
    """Get learner details with aggregated profile across all sessions."""
    try:
        db = SessionLocal()
        learner = get_learner(db, learner_id)
        if not learner:
            return _product_response(
                {"learner": None}, session_id=learner_id,
                status="error", message="Learner not found", source="db",
            )

        sessions = get_learner_sessions(db, learner_id)
        aggregated = get_learner_aggregated_profile(db, learner_id)

        # Normalize dimensions in aggregated profile
        if aggregated and aggregated.get("dimensions"):
            aggregated["dimensions"] = normalize_profile_dimensions(aggregated["dimensions"])

        return _product_response(
            {"learner": {
                "id": learner.id,
                "nickname": learner.nickname,
                "createdAt": int(learner.created_at.timestamp() * 1000) if learner.created_at else 0,
                "updatedAt": int(learner.updated_at.timestamp() * 1000) if learner.updated_at else 0,
                "sessionCount": len(sessions),
                "sessions": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "status": s.status,
                        "createdAt": int(s.created_at.timestamp() * 1000) if s.created_at else 0,
                    }
                    for s in sessions
                ],
                "aggregatedProfile": aggregated,
            }},
            session_id=learner_id, source="db",
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Resource endpoints — read from DB, trigger via POST
# ═══════════════════════════════════════════════════════════════════════


@router.get("/resources")
def get_resources(
    sessionId: str = "",
    subjectId: str = "",
    type: str = "",
    difficulty: str = "",
    source: str = "",
    search: str = "",
    knowledgePoint: str = "",
    relatedStageId: str = "",
    resourceIds: str = "",
    taskId: str = "",
    chapter: str = "",
    qualityStatus: str = "",
    studyStatus: str = "",
    bookmarked: str = "",
    sortBy: str = "default",
) -> dict[str, Any]:
    """Read resources from DB. Supports multi-condition combined filtering and sorting."""
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)
    _resource_id_set: set[str] = set()
    _resource_id_suffixes: set[str] = set()
    _bookmarked_filter: bool | None = None
    if bookmarked:
        _bookmarked_filter = bookmarked.lower() == "true"
    if resourceIds:
        for rid in resourceIds.split(","):
            rid = rid.strip()
            if rid:
                _resource_id_set.add(rid)
                _resource_id_suffixes.add(rid)
                _resource_id_set.add(f"_{rid}")

    def _matches(item: dict[str, Any]) -> bool:
        if _resource_id_set:
            item_id = item.get("id", "")
            if item_id in _resource_id_set:
                return True
            for suffix in _resource_id_suffixes:
                if item_id.endswith(f"_{suffix}") or item_id.endswith(suffix):
                    return True
            return False
        if type and item.get("type", "") != type:
            return False
        if difficulty and item.get("difficulty", "") != difficulty:
            return False
        if source:
            item_source = _source_label(item.get("source", ""))
            if item_source != source:
                return False
        if relatedStageId:
            item_stage = item.get("relatedStageId", item.get("related_stage_id", ""))
            if item_stage != relatedStageId:
                return False
        if taskId:
            item_task = item.get("taskId", item.get("task_id", ""))
            if item_task != taskId:
                return False
        if search:
            q = search.lower()
            title = (item.get("title") or "").lower()
            desc = (item.get("description") or "").lower()
            kps = " ".join(item.get("knowledgePoints", item.get("knowledge_points", []))).lower()
            item_chapter_s = (item.get("relatedChapter", item.get("related_chapter", "")) or "").lower()
            tags = " ".join(item.get("tags", [])).lower()
            if (
                q not in title
                and q not in desc
                and q not in kps
                and q not in item.get("id", "").lower()
                and q not in item_chapter_s
                and q not in tags
            ):
                return False
        if knowledgePoint:
            kps = item.get("knowledgePoints", item.get("knowledge_points", []))
            if knowledgePoint not in kps:
                return False
        if chapter:
            item_chapter = item.get("relatedChapter", item.get("related_chapter", ""))
            if chapter not in item_chapter:
                return False
        if qualityStatus:
            item_qs = item.get("qualityStatus", item.get("quality_status", ""))
            if item_qs != qualityStatus:
                return False
        if studyStatus:
            item_ss = item.get("studyStatus", item.get("study_status", "new"))
            if item_ss != studyStatus:
                return False
        if _bookmarked_filter is not None:
            if item.get("bookmarked", False) != _bookmarked_filter:
                return False
        return True

    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "type": _resource_type(item.get("type", "lecture")),
            "title": item.get("title", "学习资源"),
            "description": item.get("description", ""),
            "content": item.get("content", ""),
            "knowledgePoints": item.get("knowledgePoints", item.get("knowledge_points", [])),
            "tags": item.get("tags", []),
            "difficulty": item.get("difficulty", "easy"),
            "estimatedMinutes": item.get("estimatedMinutes", item.get("estimated_minutes", 20)),
            "format": item.get("format", "text"),
            "mermaidDef": item.get("mermaidDef", item.get("mermaid_def")),
            "codeBlocks": item.get("codeBlocks", item.get("code_blocks")),
            "questions": item.get("questions"),
            "pptOutline": item.get("pptOutline", item.get("ppt_outline")),
            "createdAt": item.get("createdAt", int(time.time() * 1000)),
            "bookmarked": item.get("bookmarked", False),
            "studyStatus": item.get("studyStatus", item.get("study_status", "new")),
            "completedAt": item.get("completedAt", item.get("completed_at")),
            "source": _source_label(item.get("source", "")),
            "relatedStageId": item.get("relatedStageId", item.get("related_stage_id", "")),
            "relatedChapterId": item.get("relatedChapterId", item.get("related_chapter_id", "")),
            "relatedSectionId": item.get("relatedSectionId", item.get("related_section_id", "")),
            "taskId": item.get("taskId", item.get("task_id", "")),
            "relatedChapter": item.get("relatedChapter", item.get("related_chapter", "")),
            "relatedKnowledgePoints": item.get("relatedKnowledgePoints", item.get("related_knowledge_points", [])),
            "qualityStatus": item.get("qualityStatus", item.get("quality_status", "")),
            "sourceType": item.get("sourceType", item.get("source_type", "")),
            "generationMode": item.get("generationMode", item.get("generation_mode", "")),
            "reason": item.get("reason", ""),
            "evidence": item.get("evidence", []),
            "fallbackReason": item.get("fallbackReason", item.get("fallback_reason", "")),
        }

    # Merge DB resources with in-memory resources
    db_resources = ag_get_resources(session_id)
    db_map: dict[str, dict[str, Any]] = {}
    if db_resources:
        bookmarks = _get_bookmarks(session_id)
        for r in db_resources:
            r["bookmarked"] = r["id"] in bookmarks
            r["createdAt"] = int(datetime.fromisoformat(r["created_at"]).timestamp() * 1000) if r.get("created_at") else int(time.time() * 1000)
            db_map[r["id"]] = _normalize(r)

    state = conversation_store.get(session_id)
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    memory_map: dict[str, dict[str, Any]] = {}
    if state and state.last_result:
        for item in state.last_result.get("resources", []):
            normalized = _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
            rid = normalized.get("id", "")
            if rid:
                memory_map[rid] = normalized

    orphaned_ids = [
        rid for rid, item in db_map.items()
        if rid not in memory_map
        and (not item.get("title") or item.get("title") in ("", "学习资源"))
    ]
    if orphaned_ids:
        try:
            from app.db.repository import delete_resource as repo_delete_resource
            db = SessionLocal()
            for oid in orphaned_ids:
                repo_delete_resource(db, session_id, oid)
            db.close()
        except Exception:
            logger.warning("Failed to clean up orphaned resources in get_resources")

        for oid in orphaned_ids:
            db_map.pop(oid, None)

    all_ids = set(db_map.keys()) | set(memory_map.keys())
    for rid in all_ids:
        db_item = db_map.get(rid)
        mem_item = memory_map.get(rid)
        if db_item and (db_item.get("title") or "").strip() and db_item.get("title") != "学习资源":
            item = db_item
        elif mem_item:
            item = {**mem_item, **(db_item or {})}
            item["id"] = rid
        elif db_item:
            item = db_item
        else:
            continue
        if _matches(item):
            seen_ids.add(rid)
            merged.append(item)

    _DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}

    def _sort_key(r: dict[str, Any]) -> tuple:
        study_status = r.get("studyStatus", "new")
        difficulty = r.get("difficulty", "easy")
        diff_order = _DIFFICULTY_ORDER.get(difficulty, 1)
        created_at = r.get("createdAt", 0)
        est_min = r.get("estimatedMinutes", 9999)
        has_stage = 0 if r.get("relatedStageId") or r.get("related_chapter") else 1
        is_completed = 0 if study_status == "completed" else 1

        if sortBy == "newest":
            return (-created_at,)
        elif sortBy == "shortest":
            return (est_min, is_completed)
        elif sortBy == "easiest":
            return (diff_order, is_completed)
        elif sortBy == "hardest":
            return (-diff_order, is_completed)
        elif sortBy == "status":
            return (is_completed, -created_at)
        elif sortBy == "stage":
            return (has_stage, is_completed, -created_at)
        else:
            return (is_completed, has_stage, -created_at)

    merged.sort(key=_sort_key)

    completed_count = sum(1 for r in merged if r.get("studyStatus") == "completed")
    total_count = len(merged)

    return _product_response(
        {
            "resources": merged,
            "total": total_count,
            "completedCount": completed_count,
            "incompleteCount": total_count - completed_count,
            "completionRate": round(completed_count / total_count * 100) if total_count > 0 else 0,
            "page": 1,
            "sessionId": session_id,
        },
        session_id=session_id, subject_id=subjectId, source="db",
    )


@router.get("/resources/{resource_id}")
def get_resource(resource_id: str, sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Get a single resource by ID — tries DB first, then in-memory fallback."""
    session_id = _resolve_session_id(sessionId, subjectId)

    db_resources = ag_get_resources(session_id)
    db_match = next((r for r in db_resources if r["id"] == resource_id), None)
    if db_match:
        bookmarks = _get_bookmarks(session_id)
        return _product_response(
            {"resource": {
                "id": db_match["id"],
                "type": _resource_type(db_match.get("type", "lecture")),
                "title": db_match.get("title", "学习资源"),
                "description": db_match.get("description", ""),
                "content": db_match.get("content", ""),
                "knowledgePoints": db_match.get("knowledge_points", []),
                "tags": db_match.get("tags", []),
                "difficulty": db_match.get("difficulty", "easy"),
                "estimatedMinutes": db_match.get("estimated_minutes", 20),
                "format": db_match.get("format", "text"),
                "mermaidDef": db_match.get("mermaid_def"),
                "codeBlocks": db_match.get("code_blocks"),
                "questions": db_match.get("questions"),
                "pptOutline": db_match.get("ppt_outline"),
                "createdAt": int(datetime.fromisoformat(db_match["created_at"]).timestamp() * 1000) if db_match.get("created_at") else int(time.time() * 1000),
                "bookmarked": db_match["id"] in bookmarks,
                "studyStatus": db_match.get("study_status", "new"),
                "source": _source_label(db_match.get("source", "")),
                "relatedStageId": db_match.get("related_stage_id", ""),
                "relatedChapterId": db_match.get("related_chapter_id", ""),
                "relatedSectionId": db_match.get("related_section_id", ""),
                "taskId": db_match.get("task_id", ""),
            }},
            session_id=session_id, subject_id=subjectId, source="db",
        )

    state = conversation_store.get(session_id)
    if state.last_result:
        resources = [
            _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
            for item in state.last_result.get("resources", [])
        ]
        match = next((item for item in resources if item["id"] == resource_id), None)
        if match:
            return _product_response({"resource": match}, session_id=session_id, subject_id=subjectId, source="memory")

    return _product_response(
        {"resource": {
            "id": resource_id,
            "type": "lecture",
            "title": "资源未找到",
            "description": "",
            "content": "",
            "source": "none",
        }},
        session_id=session_id, subject_id=subjectId, source="none",
    )


@router.post("/resources/{resource_id}/bookmark")
def bookmark_resource(resource_id: str, sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    try:
        db = SessionLocal()
        from app.db.repository import get_resource as repo_get_resource, upsert_resource as repo_upsert_resource
        state = conversation_store.get(session_id)
        if state.last_result:
            for item in state.last_result.get("resources", []):
                if item.get("resource_id") == resource_id:
                    repo_upsert_resource(db, session_id, {
                        "id": resource_id,
                        "type": item.get("type", "lecture"),
                        "title": item.get("title", "学习资源"),
                        "description": item.get("description", ""),
                        "content": item.get("content", ""),
                    })
                    break
        resource = repo_get_resource(db, session_id, resource_id)
        if resource is None:
            return _product_response(
                {"bookmarked": False, "ok": False, "error": "resource does not belong to this session"},
                session_id=session_id,
                subject_id=subjectId,
                status="error",
                message="resource does not belong to this session",
                source="user_action",
            )
        bookmarked = toggle_bookmark(db, session_id, resource_id)
        return _product_response(
            {"bookmarked": bool(bookmarked), "ok": True},
            session_id=session_id,
            subject_id=subjectId,
            source="user_action",
        )
    finally:
        db.close()


@router.patch("/resources/{resource_id}/study-status")
def update_resource_study_status(resource_id: str, payload: dict[str, Any], sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Update the study status of a resource. Only updates existing DB records."""
    session_id = _resolve_session_id(sessionId, subjectId)
    study_status = str(payload.get("studyStatus", "completed"))
    db = SessionLocal()
    try:
        from app.db.repository import get_resource as repo_get_resource, upsert_resource as repo_upsert_resource, update_resource_study_status as repo_update_status
        resource = repo_get_resource(db, session_id, resource_id)
        if resource:
            repo_update_status(db, session_id, resource_id, study_status)
            return _product_response({"ok": True, "studyStatus": study_status}, session_id=session_id, subject_id=subjectId, source="user_action")

        from app.db.models import ResourceModel
        resource_any = db.get(ResourceModel, resource_id)
        if resource_any:
            return _product_response(
                {"ok": False},
                session_id=session_id,
                subject_id=subjectId,
                status="error",
                message="resource does not belong to this session",
                source="user_action",
            )

        state = conversation_store.get(session_id)
        if state and state.last_result:
            for item in state.last_result.get("resources", []):
                rid = item.get("resource_id") or item.get("id", "")
                if rid == resource_id:
                    repo_upsert_resource(db, session_id, {
                        "id": resource_id,
                        "type": item.get("type", "lecture"),
                        "title": item.get("title", "学习资源"),
                        "description": item.get("description", ""),
                        "content": item.get("content", ""),
                        "difficulty": item.get("difficulty", "easy"),
                        "source": item.get("source", "agent_generated"),
                        "study_status": study_status,
                    })
                    return _product_response({"ok": True, "studyStatus": study_status}, session_id=session_id, subject_id=subjectId, source="user_action")

        return _product_response(
            {"ok": False},
            session_id=session_id,
            subject_id=subjectId,
            status="error",
            message="resource not found",
            source="user_action",
        )
    finally:
        db.close()


@router.post("/resources/batch/study-status")
def batch_update_study_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Batch update study status for multiple resources in a session."""
    session_id = _payload_session_id(payload)
    resource_ids: list[str] = payload.get("resourceIds", [])
    study_status = str(payload.get("studyStatus", "completed"))
    if not resource_ids:
        return _product_response({"ok": False, "updated": 0}, session_id=session_id, status="error", message="resourceIds is required", source="user_action")
    try:
        db = SessionLocal()
        from app.db.repository import batch_update_study_status as repo_batch_status
        updated = repo_batch_status(db, session_id, resource_ids, study_status)
        return _product_response({"ok": True, "updated": updated, "studyStatus": study_status}, session_id=session_id, source="user_action")
    finally:
        db.close()


@router.post("/resources/batch/bookmark")
def batch_set_bookmark(payload: dict[str, Any]) -> dict[str, Any]:
    """Batch bookmark or un-bookmark multiple resources in a session."""
    session_id = _payload_session_id(payload)
    resource_ids: list[str] = payload.get("resourceIds", [])
    bookmarked = bool(payload.get("bookmarked", True))
    if not resource_ids:
        return _product_response({"ok": False, "updated": 0}, session_id=session_id, status="error", message="resourceIds is required", source="user_action")
    try:
        db = SessionLocal()
        from app.db.repository import batch_set_bookmark as repo_batch_bookmark
        updated = repo_batch_bookmark(db, session_id, resource_ids, bookmarked)
        return _product_response({"ok": True, "updated": updated, "bookmarked": bookmarked}, session_id=session_id, source="user_action")
    finally:
        db.close()


@router.post("/resources/batch/export")
def batch_export_resources(payload: dict[str, Any]) -> dict[str, Any]:
    """Export resource titles as a text list. Optionally filter by resourceIds."""
    session_id = _payload_session_id(payload)
    resource_ids: list[str] | None = payload.get("resourceIds")

    db_resources = ag_get_resources(session_id)
    db_map: dict[str, dict[str, Any]] = {r["id"]: r for r in db_resources}

    state = conversation_store.get(session_id)
    memory_resources: list[dict[str, Any]] = []
    if state and state.last_result:
        for item in state.last_result.get("resources", []):
            normalized = _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
            rid = normalized.get("id", "")
            if rid and rid not in db_map:
                db_map[rid] = normalized

    if resource_ids:
        id_set = set(resource_ids)
        items = [r for rid, r in db_map.items() if rid in id_set]
    else:
        items = list(db_map.values())

    lines: list[str] = []
    for i, r in enumerate(items, 1):
        title = r.get("title", "未命名资源")
        rtype = r.get("type", "lecture")
        diff = r.get("difficulty", "easy")
        chapter = r.get("relatedChapter", r.get("related_chapter", ""))
        status = r.get("studyStatus", r.get("study_status", "new"))
        status_label = {"new": "未开始", "in_progress": "学习中", "completed": "已完成"}.get(status, status)
        chapter_part = f" [{chapter}]" if chapter else ""
        lines.append(f"{i:3d}. [{rtype}] {title}{chapter_part} ({diff}) — {status_label}")

    export_text = "\n".join(lines)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    header = f"EduAgent 资源导出 — {timestamp}\n共 {len(items)} 项资源\n{'─' * 48}\n"
    return _product_response({"ok": True, "export": header + export_text, "count": len(items)}, session_id=session_id, source="user_action")


@router.post("/resources/generate")
def generate_resource(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    """Trigger agent pipeline to generate resources for a topic."""
    session_id = _payload_session_id(payload)
    topic = str(payload.get("topic", "学习主题"))
    resource_type = str(payload.get("type", "")).strip()
    difficulty = str(payload.get("difficulty", "")).strip()
    subject_id = str(payload.get("subjectId", "")).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    parts = [f"请为「{topic}」"]
    if resource_type:
        type_labels = {
            "lecture": "生成一份课程讲义",
            "mindmap": "生成一份思维导图（Mermaid mindmap 格式）",
            "quiz": "生成一套练习题（含答案和解析）",
            "reading": "生成一份拓展阅读材料",
            "case_study": "生成一个实操案例（含代码示例）",
            "video": "生成一份教学视频脚本/动画大纲",
            "ppt": "生成一份PPT大纲",
        }
        parts.append(type_labels.get(resource_type, f"生成{resource_type}类型的资源"))
    else:
        parts.append("生成学习资源")
    if difficulty and difficulty in ("easy", "medium", "hard"):
        diff_labels = {"easy": "入门难度", "medium": "中等难度", "hard": "进阶难度"}
        parts.append(f"难度为{diff_labels[difficulty]}")
    if subject_id:
        parts.append(f"所属科目ID为{subject_id}")
    message = "，".join(parts)

    result = _run_agents(message, session_id=session_id)
    resources = [
        _to_resource(item, result.get("course_id", "ai_intro"), session_id)
        for item in result.get("resources", [])
    ]
    primary = resources[0] if resources else {"id": "res_new", "title": f"{topic} 个性化资源", "source": "none"}
    return _product_response({"resource": primary}, session_id=session_id, source="agent")


@router.post("/resources/import-from-kb")
def import_resources_from_kb(payload: dict[str, Any]) -> dict[str, Any]:
    """Import knowledge base chapters directly as resources."""
    session_id = _payload_session_id(payload)
    course_id = str(payload.get("courseId", "")).strip()
    subject_id = str(payload.get("subjectId", "")).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    if course_id:
        course = course_catalog.get_course(course_id)
    else:
        available = course_catalog.list_courses()
        course = available[0] if available else None

    if not course:
        return _product_response(
            {"imported": 0, "resources": []},
            session_id=session_id,
            subject_id=subject_id,
            message="No course found in knowledge base",
            source="kb_import",
        )

    course_name = course.get("course_name", course_id or "课程")
    chapters = course.get("chapters", [])
    imported: list[dict[str, Any]] = []

    try:
        db = SessionLocal()
        from app.db.repository import upsert_resource as repo_upsert

        for idx, chapter in enumerate(chapters, start=1):
            chapter_id = str(chapter.get("chapter_id", str(idx).zfill(2)))
            detail = course_catalog.load_chapter(
                course.get("course_id", course_id), chapter_id
            )
            content = str(detail.get("content", "")) if detail else ""
            title = str(chapter.get("title", f"第{idx}章"))
            difficulty = str(chapter.get("difficulty", "medium"))

            resource_id = f"{session_id}_kb_{course.get('course_id', 'kb')}_{chapter_id}"
            resource_data = {
                "id": resource_id,
                "type": "lecture",
                "title": f"{title}（课程讲义）",
                "description": f"来自课程「{course_name}」第{idx}章：{title}",
                "content": content if content else f"## {title}\n\n课程章节内容。",
                "knowledge_points": [title],
                "tags": ["knowledge_base", course_name, "auto_import"],
                "difficulty": difficulty,
                "estimated_minutes": max(15, len(content) // 300 * 5) if content else 20,
                "format": "markdown",
                "source": "knowledge_base",
                "related_chapter": title,
                "study_status": "new",
                "quality_status": "passed",
            }
            repo_upsert(db, session_id, resource_data)
            imported.append({
                "id": resource_id,
                "type": "lecture",
                "title": resource_data["title"],
                "description": resource_data["description"],
                "difficulty": difficulty,
            })

        all_titles = [str(ch.get("title", "")) for ch in chapters]
        mindmap_id = f"{session_id}_kb_{course.get('course_id', 'kb')}_mindmap"
        mindmap_lines = ["mindmap", f"  root(({course_name}))"]
        for t in all_titles[:8]:
            mindmap_lines.append(f"    {t}")
        repo_upsert(db, session_id, {
            "id": mindmap_id,
            "type": "mindmap",
            "title": f"{course_name}知识结构图",
            "description": f"课程「{course_name}」全部章节知识结构图",
            "content": "\n".join(mindmap_lines),
            "knowledge_points": all_titles,
            "tags": ["knowledge_base", course_name, "auto_import"],
            "difficulty": "easy",
            "estimated_minutes": 5,
            "format": "mermaid",
            "source": "knowledge_base",
            "study_status": "new",
            "quality_status": "passed",
        })
        imported.append({
            "id": mindmap_id, "type": "mindmap",
            "title": f"{course_name}知识结构图",
            "description": "全部章节结构图",
        })

        reading_id = f"{session_id}_kb_{course.get('course_id', 'kb')}_reading"
        reading_lines = ["## 课程阅读顺序\n"]
        for i, t in enumerate(all_titles, 1):
            reading_lines.append(f"{i}. 阅读「{t}」并整理核心概念和常见误区")
        repo_upsert(db, session_id, {
            "id": reading_id,
            "type": "reading",
            "title": f"{course_name}拓展阅读路径",
            "description": f"课程「{course_name}」章节阅读顺序",
            "content": "\n".join(reading_lines),
            "knowledge_points": all_titles,
            "tags": ["knowledge_base", course_name, "auto_import"],
            "difficulty": "easy",
            "estimated_minutes": 10,
            "format": "markdown",
            "source": "knowledge_base",
            "study_status": "new",
            "quality_status": "passed",
        })
        imported.append({
            "id": reading_id, "type": "reading",
            "title": f"{course_name}拓展阅读路径",
            "description": "章节阅读顺序",
        })

        return _product_response(
            {"imported": len(imported), "resources": imported},
            session_id=session_id,
            subject_id=subject_id,
            source="kb_import",
        )
    finally:
        db.close()


@router.get("/resources/{resource_id}/knowledge-graph")
def resource_knowledge_graph(resource_id: str, sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    resource = _find_resource_for_graph(resource_id, session_id)
    if not resource:
        return _product_response(
            {"mermaidDef": "", "source": "none", "resourceId": resource_id},
            session_id=session_id, subject_id=subjectId, source="none",
        )

    existing = str(resource.get("mermaidDef") or resource.get("mermaid_def") or "").strip()
    if existing:
        return _product_response(
            {
                "mermaidDef": existing,
                "source": _source_label(str(resource.get("source", ""))),
                "resourceId": resource_id,
            },
            session_id=session_id, subject_id=subjectId, source="db",
        )

    title = str(resource.get("title") or resource_id).strip()
    knowledge_points = [
        str(item).strip()
        for item in resource.get("knowledgePoints", resource.get("knowledge_points", [])) or []
        if str(item).strip()
    ]
    tags = [str(item).strip() for item in resource.get("tags", []) or [] if str(item).strip()]
    children = knowledge_points or tags or [str(resource.get("type") or "resource")]
    lines = ["mindmap", f"  root(({_safe_mermaid_label(title)}))"]
    for child in children[:8]:
        lines.append(f"    {_safe_mermaid_label(child)}")
    return _product_response(
        {
            "mermaidDef": "\n".join(lines),
            "source": _source_label(str(resource.get("source", ""))),
            "resourceId": resource_id,
        },
        session_id=session_id, subject_id=subjectId, source="generated",
    )


def _find_resource_for_graph(resource_id: str, session_id: str) -> dict[str, Any] | None:
    db_match = next((item for item in ag_get_resources(session_id) if item.get("id") == resource_id), None)
    if db_match:
        return {
            "id": db_match.get("id"),
            "type": db_match.get("type"),
            "title": db_match.get("title"),
            "knowledgePoints": db_match.get("knowledge_points", []),
            "tags": db_match.get("tags", []),
            "mermaidDef": db_match.get("mermaid_def"),
            "source": db_match.get("source"),
        }

    state = conversation_store.get(session_id)
    if state.last_result:
        for item in state.last_result.get("resources", []):
            if item.get("resource_id") == resource_id or item.get("id") == resource_id:
                return _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
    return None


def _safe_mermaid_label(text: str) -> str:
    cleaned = re.sub(r"[\r\n\t]+", " ", text).strip()
    cleaned = cleaned.replace("(", "（").replace(")", "）").replace(":", "：")
    return cleaned[:48] or "resource"


@router.get("/resources/{resource_id}/knowledge-graph-legacy")
def resource_knowledge_graph_legacy(resource_id: str) -> dict[str, Any]:
    return _product_response(
        {"mermaidDef": (
            "mindmap\n"
            "  root((人工智能导论))\n"
            "    机器学习基础\n"
            "    神经网络\n"
            "    自然语言处理\n"
            f"    资源 {resource_id}"
        )},
        source="mock",
    )


# ── In-memory node progress store ────────────────────────────────────
_node_progress_store: dict[str, dict[str, Any]] = {}


def _nkey(session_id: str, node_id: str) -> str:
    return f"{session_id}:{node_id}"


def _apply_node_progress(stages: list[dict[str, Any]], session_id: str = "") -> list[dict[str, Any]]:
    if not session_id:
        return stages
    for stage in stages:
        for node in stage.get("nodes", []):
            nid = node["id"]
            try:
                from app.db.engine import SessionLocal as _DL
                from app.db.models import ResourceModel as _RM
                from sqlalchemy import select, func as _F
                _db = _DL()
                total = _db.execute(
                    select(_F.count(_RM.id))
                    .where(_RM.session_id == session_id)
                    .where(_RM.task_id == nid)
                ).scalar() or 0
                completed = _db.execute(
                    select(_F.count(_RM.id))
                    .where(_RM.session_id == session_id)
                    .where(_RM.task_id == nid)
                    .where(_RM.study_status == "completed")
                ).scalar() or 0
                _db.close()
            except Exception:
                total = 0
                completed = 0

            if total > 0 and completed >= total:
                node["status"] = "mastered"
                node["mastery"] = 100
            elif completed > 0:
                node["status"] = "in_progress"
                node["mastery"] = 60
            elif _nkey(session_id, nid) in _node_progress_store:
                saved = _node_progress_store[_nkey(session_id, nid)]
                node["status"] = saved.get("status", node["status"])
                node["mastery"] = 0
            if node.get("mastery", 0) >= 100 and node.get("status") != "mastered":
                node["mastery"] = 60

    for i, stage in enumerate(stages):
        nodes = stage.get("nodes", [])
        if not nodes:
            continue
        all_mastered = all(n.get("status") == "mastered" for n in nodes)
        if all_mastered and i + 1 < len(stages):
            next_stage = stages[i + 1]
            next_nodes = next_stage.get("nodes", [])
            if next_nodes and next_nodes[0].get("status") not in ("mastered", "in_progress"):
                first_next = next_nodes[0]["id"]
                if _nkey(session_id, first_next) not in _node_progress_store:
                    _node_progress_store[_nkey(session_id, first_next)] = {
                        "status": "available", "mastery": 0,
                        "updatedAt": time.time(),
                    }
                    _log_node_progress(session_id, first_next, "available")
                next_nodes[0]["status"] = "available"

    # Apply saved progress to chapter hierarchy
    for stage in stages:
        for chapter in stage.get("chapters", []):
            ch_id = chapter.get("chapter_id") or chapter.get("id", "")
            if ch_id and _nkey(session_id, ch_id) in _node_progress_store:
                saved = _node_progress_store[_nkey(session_id, ch_id)]
                chapter["status"] = saved.get("status", chapter.get("status", "not_started"))
            for section in chapter.get("sections", []):
                sec_id = section.get("section_id") or section.get("id", "")
                if sec_id and _nkey(session_id, sec_id) in _node_progress_store:
                    saved = _node_progress_store[_nkey(session_id, sec_id)]
                    section["status"] = saved.get("status", section.get("status", "not_started"))
                for kp in section.get("knowledge_points", []):
                    kp_id = kp.get("kp_id") or kp.get("id", "")
                    if kp_id and _nkey(session_id, kp_id) in _node_progress_store:
                        saved = _node_progress_store[_nkey(session_id, kp_id)]
                        kp["status"] = saved.get("status", kp.get("status", "not_started"))
                        kp["mastery"] = saved.get("mastery", kp.get("mastery", 0))

    return stages


# ═══════════════════════════════════════════════════════════════════════
# Learning path endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/learning-path")
def get_learning_path(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    def _build_path(stages: list[dict[str, Any]], base: dict[str, Any]) -> dict[str, Any]:
        stages = _apply_node_progress(stages, session_id)
        all_nodes = [n for s in stages for n in s.get("nodes", [])]
        mastered = sum(1 for n in all_nodes if n.get("status") == "mastered")
        overall = round(mastered / len(all_nodes) * 100) if all_nodes else 0

        stage_resource_stats: dict[str, dict[str, int]] = {}
        stage_ids = [s.get("id", "") for s in stages]
        try:
            db_res = ag_get_resources(session_id)
            for r in db_res:
                sid = r.get("related_stage_id", "") or r.get("relatedStageId", "")
                if not sid:
                    continue
                matched = next((s for s in stage_ids if sid in s or s in sid), None)
                if not matched:
                    continue
                if matched not in stage_resource_stats:
                    stage_resource_stats[matched] = {"total": 0, "completed": 0}
                stage_resource_stats[matched]["total"] += 1
                if r.get("study_status") == "completed":
                    stage_resource_stats[matched]["completed"] += 1
        except Exception:
            logger.warning("Failed to compute resource stats for stages")

        return {
            "id": base.get("id", f"path_{session_id}"),
            "title": base.get("title", "个性化学习路径"),
            "description": base.get("description", ""),
            "courseName": base.get("courseName", ""),
            "courseId": base.get("courseId", ""),
            "stages": stages,
            "stageResourceStats": stage_resource_stats,
            "createdAt": base.get("createdAt", int(time.time() * 1000)),
            "overallProgress": overall,
            "estimatedDays": base.get("estimatedDays", 14),
            "source": "agent_generated",
        }

    db_path = ag_get_learning_path(session_id)
    if db_path:
        raw_stages = db_path.get("stages", [])
        if isinstance(raw_stages, list):
            stages = _raw_stages_to_nodes(raw_stages)
        else:
            stages = []
        if not stages:
            return _product_response({"path": _empty_learning_path(session_id)}, session_id=session_id, subject_id=subjectId, source="none")
        return _product_response(
            {"path": _build_path(stages, {
                "id": db_path.get("id", f"path_{session_id}"),
                "title": f"{db_path.get('course_name', '')}个性化学习路径",
                "description": db_path.get("description", ""),
                "courseName": db_path.get("course_name", ""),
                "courseId": db_path.get("course_id", ""),
                "createdAt": _datetime_to_ms(db_path.get("created_at")),
                "estimatedDays": db_path.get("estimated_days", 14),
            })},
            session_id=session_id, subject_id=subjectId, source="db",
        )

    state = conversation_store.get(session_id)
    if state.last_result:
        path = _to_learning_path(state.last_result)
        if not path.get("stages"):
            return _product_response({"path": _empty_learning_path(session_id)}, session_id=session_id, subject_id=subjectId, source="none")
        path["source"] = "agent_generated"
        path["stages"] = _apply_node_progress(path["stages"], session_id)
        all_nodes = [n for s in path["stages"] for n in s.get("nodes", [])]
        mastered = sum(1 for n in all_nodes if n.get("status") == "mastered")
        path["overallProgress"] = round(mastered / len(all_nodes) * 100) if all_nodes else 0
        return _product_response({"path": path}, session_id=session_id, subject_id=subjectId, source="agent")

    return _product_response({"path": _empty_learning_path(session_id)}, session_id=session_id, subject_id=subjectId, source="none")


@router.post("/learning-path/generate")
def generate_learning_path(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    user_message = str(payload.get("userMessage", "")).strip()
    course_id = str(payload.get("courseId", "")).strip()
    subject_id = str(payload.get("subjectId", "")).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    state = conversation_store.get(session_id)

    if user_message:
        message = user_message
        if course_id:
            selected = course_catalog.get_course(course_id)
            if selected:
                message = (
                    f"目标课程：{selected.get('course_name', course_id)}。{message}"
                )
    else:
        message = conversation_store.profile_prompt(state, latest_message="请生成学习路径")

    result = _run_agents(message, session_id=session_id)
    path = _to_learning_path(result)
    return _product_response({"path": path}, session_id=session_id, source="agent")


@router.patch("/learning-path/nodes/{node_id}")
def update_node_progress(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    _node_progress_store[_nkey(session_id, node_id)] = {
        "status": payload.get("status", "available"),
        "mastery": payload.get("mastery", 0),
        "updatedAt": time.time(),
    }
    learning_tracker.log(
        {"event": "node_progress", "resourceId": node_id, "metadata": payload},
        session_id=session_id,
    )
    return _product_response({"ok": True}, session_id=session_id, source="user_action")


# ═══════════════════════════════════════════════════════════════════════
# Feedback & analytics
# ═══════════════════════════════════════════════════════════════════════


@router.post("/feedback")
def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    learning_tracker.log({"event": "feedback", **payload}, session_id=session_id)
    return _product_response({"ok": True}, session_id=session_id, source="user_action")


_VALID_EVENT_TYPES: frozenset[str] = frozenset({
    "resource_view", "resource_complete", "quiz_result",
    "practice_result", "node_progress", "feedback",
})


@router.post("/feedback/event")
def log_study_event(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _payload_session_id(payload)

    event_type = payload.get("event", "")
    if event_type not in _VALID_EVENT_TYPES:
        raise InvalidEventTypeError(event_type)

    if payload.get("subjectId"):
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata = dict(metadata)
            metadata["subjectId"] = payload["subjectId"]
            payload["metadata"] = metadata

    if payload.get("event") == "resource_complete" and payload.get("resourceId"):
        try:
            from app.db.repository import get_resource as _get_res
            db = SessionLocal()
            res = _get_res(db, session_id, payload["resourceId"])
            if (
                res
                and res.session_id == session_id
                and res.estimated_minutes
                and not payload.get("duration")
            ):
                payload["duration"] = res.estimated_minutes
            db.close()
        except Exception:
            logger.warning("Failed to auto-fill duration for resource %s in session %s",
                           payload.get("resourceId", "?"), session_id)
    learning_tracker.log(payload, session_id=session_id)
    return _product_response({"ok": True}, session_id=session_id, source="user_action")


def _log_node_progress(session_id: str, node_id: str, status: str) -> None:
    try:
        stage_title = ""
        node_name = ""
        stage_id_part = node_id.rsplit("_node_", 1)[0] if "_node_" in node_id else ""
        if stage_id_part:
            try:
                from app.services.agent_service import get_learning_path as _lp
                path = _lp(session_id)
                if path:
                    for stage in path.get("stages", []):
                        sid = stage.get("id", "")
                        if sid and stage_id_part in sid:
                            stage_title = stage.get("title", "")
                            for n in stage.get("nodes", []):
                                if n.get("id") == node_id:
                                    node_name = n.get("topic", "")
                                    break
                            break
            except Exception:
                logger.warning("Failed to enrich stage title for node %s in session %s", node_id, session_id)
        learning_tracker.log({
            "event": "node_progress",
            "resourceId": node_id,
            "sessionId": session_id,
            "metadata": {
                "nodeId": node_id,
                "nodeName": node_name or "",
                "status": status,
                "stageTitle": stage_title or "",
                "relatedStageId": stage_id_part,
            },
        }, session_id=session_id)
    except Exception:
        logger.warning("Failed to log node progress for session %s", session_id)


@router.patch("/learning-path/auto-advance")
def auto_advance_node(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    related_stage_id = str(payload.get("relatedStageId", ""))
    task_id = str(payload.get("taskId", "")).strip()
    event = str(payload.get("event", ""))
    if not related_stage_id or event not in ("resource_view", "resource_complete"):
        return _product_response({"ok": False}, session_id=session_id, status="error", message="relatedStageId and valid event required", source="system")

    if task_id and not task_id.startswith(related_stage_id):
        task_id = ""

    def _update(node_id: str, status: str, mastery: int) -> None:
        _node_progress_store[_nkey(session_id, node_id)] = {
            "status": status, "mastery": mastery,
            "updatedAt": time.time(),
        }

    def _has(node_id: str) -> bool:
        return _nkey(session_id, node_id) in _node_progress_store

    if task_id and event == "resource_view":
        if not _has(task_id):
            _update(task_id, "in_progress", 40)
            _log_node_progress(session_id, task_id, "in_progress")
        parts = task_id.rsplit("_node_", 1)
        if len(parts) == 2:
            next_num = int(parts[1]) + 1
            next_id = f"{parts[0]}_node_{next_num}"
            if not _has(next_id):
                _update(next_id, "available", 0)
                _log_node_progress(session_id, next_id, "available")
    elif task_id and event == "resource_complete":
        parts = task_id.rsplit("_node_", 1)
        if len(parts) == 2:
            next_num = int(parts[1]) + 1
            next_id = f"{parts[0]}_node_{next_num}"
            if not _has(next_id):
                _update(next_id, "available", 0)
                _log_node_progress(session_id, next_id, "available")
        _log_node_progress(session_id, task_id, "completed")

        try:
            from app.services.agent_service import get_learning_path as _get_lp
            path = _get_lp(session_id)
            if path and path.get("stages"):
                for stage in path["stages"]:
                    sid = stage.get("id", "")
                    if sid and related_stage_id in sid:
                        nodes = stage.get("nodes", [])
                        all_completed = all(
                            _has(node.get("id", ""))
                            and _node_progress_store.get(_nkey(session_id, node.get("id", "")), {}).get("status") == "completed"
                            for node in nodes
                        ) if nodes else True
                        if all_completed and nodes:
                            learning_tracker.log({
                                "event": "stage_complete",
                                "resourceId": sid,
                                "sessionId": session_id,
                                "metadata": {
                                    "stageId": sid,
                                    "stageTitle": stage.get("title", ""),
                                    "relatedStageId": sid,
                                },
                            }, session_id=session_id)
        except Exception:
            logger.warning("Failed to track stage completion for session %s", session_id)
    return _product_response({"ok": True}, session_id=session_id, source="system")


# ── Daily Tasks ──────────────────────────────────────────────────────────


def _compute_current_day(created_at, max_days: int) -> int:
    """Compute which day of the plan we're on.

    Day 1 = the plan's creation date.
    Returns a value between 1 and max_days (inclusive).
    """
    from datetime import datetime, timezone as _tz
    if created_at is None:
        return 1
    now = datetime.now(_tz.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=_tz.utc)
    delta = (now - created_at).days
    current_day = delta + 1
    return max(1, min(current_day, max_days))


def _task_to_dict(task: "DailyTaskModel", sess: "SessionModel") -> dict[str, Any]:
    """Convert a DailyTaskModel + SessionModel to a response dict."""
    return {
        "id": task.id,
        "sessionId": sess.id,
        "subjectId": sess.subject_id or "",
        "subjectName": sess.title or "未命名科目",
        "stageId": task.stage_id,
        "dayIndex": task.day_index,
        "dayLabel": task.day_label,
        "title": task.title,
        "description": task.description,
        "completed": bool(task.completed) if task.completed is not None else False,
        "completedAt": int(task.completed_at.timestamp() * 1000) if task.completed_at else None,
        "source": task.source,
    }


@router.get("/daily-tasks/today")
def get_todays_daily_tasks(
    learnerId: str = "",
    sessionId: str = "",
    subjectId: str = "",
) -> dict[str, Any]:
    """Get all daily tasks for TODAY across all subjects for a learner.

    If learnerId is provided, aggregates across all sessions for that learner.
    If only sessionId is provided, returns tasks for that single session.
    At least one of learnerId or sessionId must be provided.
    """
    if not learnerId and not sessionId:
        raise MissingSessionIdError("learnerId or sessionId required")

    today_tasks: list[dict[str, Any]] = []
    completed_count = 0

    db = SessionLocal()
    try:
        sessions_to_scan: list[SessionModel] = []

        if learnerId:
            sessions_to_scan = repo_list_sessions(db, learner_id=learnerId)
        elif sessionId:
            sess = get_or_create_session(db, sessionId, subject_id=subjectId or None)
            sessions_to_scan = [sess]

        for sess in sessions_to_scan:
            lp = repo_get_latest_learning_path(db, sess.id)
            if not lp:
                continue

            current_day = _compute_current_day(
                lp.created_at, lp.estimated_days or 14
            )

            tasks = repo_get_daily_tasks(db, sess.id, day_index=current_day)
            for t in tasks:
                task_data = _task_to_dict(t, sess)
                task_data["courseName"] = lp.course_name or ""
                today_tasks.append(task_data)
                if t.completed:
                    completed_count += 1

        from datetime import datetime, timezone as _tz
        today_str = datetime.now(_tz.utc).strftime("%Y-%m-%d")

        return _product_response(
            {
                "tasks": today_tasks,
                "todayDate": today_str,
                "completedCount": completed_count,
                "totalCount": len(today_tasks),
            },
            session_id=sessionId or "",
            source="db",
        )
    finally:
        db.close()


@router.patch("/daily-tasks/{task_id}/complete")
def complete_daily_task(
    task_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Toggle completion status of a daily task.

    Subject isolation: the sessionId in the payload must match the
    task's session_id.  This prevents cross-subject manipulation.
    """
    session_id = _payload_session_id(payload)
    completed = bool(payload.get("completed", True))

    db = SessionLocal()
    try:
        task = repo_update_task_completion(db, task_id, session_id, completed=completed)
        if task is None:
            raise NotFoundError(
                f"Daily task {task_id} not found or session mismatch",
                resource="daily_task",
                resource_id=str(task_id),
            )
        sess = db.get(SessionModel, session_id)
        return _product_response(
            {
                "ok": True,
                "task": _task_to_dict(task, sess) if sess else None,
            },
            session_id=session_id,
            source="user_action",
        )
    finally:
        db.close()


@router.get("/learning-path/{raw_session_id}/daily-tasks")
def get_session_daily_tasks(
    raw_session_id: str,
    day: int | None = None,
    sessionId: str = "",
    subjectId: str = "",
) -> dict[str, Any]:
    """Get daily tasks for a specific session/learning path.

    Optionally filter by day_index.  If no day specified, returns tasks
    for the computed current day.
    """
    session_id = _resolve_session_id(sessionId or raw_session_id, subjectId)

    db = SessionLocal()
    try:
        lp = repo_get_latest_learning_path(db, session_id)
        if not lp:
            return _product_response(
                {"tasks": [], "dayCount": 0, "currentDay": 1},
                session_id=session_id,
                source="none",
            )

        day_index = day if day is not None else _compute_current_day(
            lp.created_at, lp.estimated_days or 14
        )

        tasks = repo_get_daily_tasks(db, session_id, day_index=day_index)
        sess = db.get(SessionModel, session_id)

        return _product_response(
            {
                "tasks": [_task_to_dict(t, sess) for t in tasks] if sess else [],
                "dayCount": lp.estimated_days or 14,
                "currentDay": day_index,
                "courseName": lp.course_name or "",
            },
            session_id=session_id,
            source="db",
        )
    finally:
        db.close()


@router.get("/learning-analytics")
def learning_analytics(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)

    analytics = ag_get_analytics(session_id)
    state = conversation_store.get(session_id)
    last_result = state.last_result or {}

    # ── M6: 能力热力图数据 ──
    diagnosis = last_result.get("diagnosis", {}) if isinstance(last_result, dict) else {}
    mastery_levels = diagnosis.get("mastery_levels", []) or []
    heatmap = [
        {"knowledgePoint": m.get("name", ""), "mastery": m.get("score", 50),
         "level": m.get("level", "初步"), "evidenceCount": m.get("evidence_count", 0)}
        for m in mastery_levels if isinstance(m, dict)
    ]

    # ── M6: 薄弱榜单 Top 5 ──
    weak_kps = diagnosis.get("weak_knowledge_points", []) or []
    recommended_strategy = diagnosis.get("recommended_strategy", "")
    weakness_ranking = []
    for w in weak_kps[:5]:
        if not isinstance(w, dict):
            continue
        # 智能建议：优先用知识点级别的 next_actions，其次用诊断级别策略
        topic_actions = w.get("next_actions") or w.get("recommended_actions") or []
        resource_ids = w.get("recommended_resource_ids") or []
        if topic_actions and isinstance(topic_actions, list) and len(topic_actions) > 0:
            suggested = f"建议：{'；'.join(str(a) for a in topic_actions[:2])}"
        elif resource_ids and len(resource_ids) > 0:
            suggested = f"推荐 {len(resource_ids)} 个匹配资源进行针对性学习"
        elif recommended_strategy:
            suggested = str(recommended_strategy)
        else:
            # 根据优先级给不同建议措辞
            p = w.get("priority", "medium")
            suggested = {"high": "优先攻克，建议每日专项练习", "medium": "按学习路径顺序逐步强化", "low": "在完成主要任务后选择性复习"}.get(p, "建议针对性练习")
        weakness_ranking.append({
            "name": w.get("name", ""),
            "priority": w.get("priority", "medium"),
            "reason": w.get("reason", ""),
            "suggested_action": suggested,
            "resourceIds": resource_ids[:3] if isinstance(resource_ids, list) else [],
        })

    # ── M6: 从 DB 拉取近30天的学习事件用于按日统计 ──
    from datetime import datetime, timedelta, date as date_type
    today = date_type.today()
    thirty_days_ago = today - timedelta(days=29)

    # 按日期聚合：{ "YYYY-MM-DD": { "questionCount": int, "accuracySum": float, "active": bool } }
    daily_stats: dict[str, dict[str, Any]] = {}
    for day_offset in range(29, -1, -1):
        d = today - timedelta(days=day_offset)
        key = d.strftime("%Y-%m-%d")
        daily_stats[key] = {"questionCount": 0, "accuracySum": 0.0, "active": False}

    try:
        try:
            db_events = SessionLocal()
            from app.db.models import LearningEventModel
            from sqlalchemy import and_

            rows = (
                db_events.query(LearningEventModel)
                .filter(
                    and_(
                        LearningEventModel.session_id == session_id,
                        LearningEventModel.created_at >= thirty_days_ago,
                        LearningEventModel.event_type.in_([
                            "quiz_result", "quiz_submit", "practice_result",
                            "resource_view", "resource_complete",
                        ]),
                    )
                )
                .order_by(LearningEventModel.created_at.asc())
                .all()
            )
            for row in rows:
                if row.created_at:
                    day_key = row.created_at.strftime("%Y-%m-%d")
                    if day_key in daily_stats:
                        daily_stats[day_key]["active"] = True
                        meta = row.metadata_ or {}
                        if row.event_type in ("quiz_result", "quiz_submit", "practice_result"):
                            daily_stats[day_key]["questionCount"] += 1
                            score = None
                            if "accuracy" in meta:
                                try:
                                    a = float(meta["accuracy"])
                                    score = round(a * 100) if a <= 1 else round(a)
                                except (TypeError, ValueError):
                                    pass
                            if score is None and "score" in meta:
                                try:
                                    s = float(meta["score"])
                                    score = round(s * 100) if s <= 1 else round(s)
                                except (TypeError, ValueError):
                                    pass
                            if score is None and "correct" in meta and "total" in meta:
                                try:
                                    c = int(meta["correct"])
                                    t = int(meta["total"])
                                    if t > 0:
                                        score = round(c / t * 100)
                                except (TypeError, ValueError):
                                    pass
                            if score is not None:
                                daily_stats[day_key]["accuracySum"] += score
        finally:
            db_events.close()
    except Exception as e:
        logger.warning(f"Failed to query DB for daily stats: {e}")

    # ── M6: 进步曲线（近30天正确率+做题量）──
    progress_curve = []
    for day_offset in range(29, -1, -1):
        d = today - timedelta(days=day_offset)
        key = d.strftime("%Y-%m-%d")
        ds = daily_stats.get(key, {})
        qc = ds.get("questionCount", 0)
        acc_sum = ds.get("accuracySum", 0.0)
        progress_curve.append({
            "date": d.strftime("%m-%d"),
            "accuracy": round(acc_sum / qc) if qc > 0 else None,
            "questionCount": qc,
        })

    # ── M6: 学习日历（最近30天活跃日+表现等级）──
    study_calendar = []
    for day_offset in range(29, -1, -1):
        d = today - timedelta(days=day_offset)
        key = d.strftime("%Y-%m-%d")
        ds = daily_stats.get(key, {})
        qc = ds.get("questionCount", 0)
        active = ds.get("active", False)
        # 表现等级：无活动=0, 有活动无答题=1, 正确率<60=2, 正确率≥60=3, 正确率≥80=4
        perf_level = 0
        if active:
            perf_level = 1
            if qc > 0:
                acc_sum = ds.get("accuracySum", 0.0)
                avg_acc = acc_sum / qc
                if avg_acc >= 80:
                    perf_level = 4
                elif avg_acc >= 60:
                    perf_level = 3
                else:
                    perf_level = 2
        study_calendar.append({
            "date": key,
            "active": active,
            "questionCount": qc,
            "performanceLevel": perf_level,
        })

    # ── M6: 今日统计 ──
    today_key = today.strftime("%Y-%m-%d")
    today_ds = daily_stats.get(today_key, {})
    today_questions = today_ds.get("questionCount", 0)
    today_acc_sum = today_ds.get("accuracySum", 0.0)
    today_avg_score = round(today_acc_sum / today_questions) if today_questions > 0 else None

    # ── M6: 目标追踪 ──
    learning_path = last_result.get("learning_path", []) if isinstance(last_result, dict) else []
    exam_date_str = last_result.get("examDate") if isinstance(last_result, dict) else None
    days_until_exam = None
    if exam_date_str:
        try:
            exam_date = datetime.strptime(str(exam_date_str), "%Y-%m-%d").date()
            days_until_exam = (exam_date - today).days
        except (ValueError, TypeError):
            pass

    # 预估达成分位：基于掌握度加权
    mastery_scores = [m.get("score", 0) for m in mastery_levels if isinstance(m, dict)]
    avg_mastery = int(sum(mastery_scores) / max(1, len(mastery_scores)))
    # 简单估算：掌握度每10分一档，映射到分位
    estimated_percentile = min(99, max(1, avg_mastery + (10 if avg_mastery >= 70 else -5)))

    # 进度条：完成阶段数 / 总阶段数
    stages_total = len(learning_path)
    stages_done = last_result.get("currentStageIndex", 0) if isinstance(last_result, dict) else 0
    if isinstance(stages_done, int) and stages_total > 0:
        progress_pct = round(stages_done / stages_total * 100)
    elif avg_mastery > 0:
        progress_pct = avg_mastery
    else:
        progress_pct = 0

    goal_tracking = {
        "estimatedDays": last_result.get("estimatedDays", 14) if isinstance(last_result, dict) else 14,
        "questionsCompleted": sum(ds.get("questionCount", 0) for ds in daily_stats.values()),
        "masteryPercentage": avg_mastery,
        "stagesCompleted": stages_done if isinstance(stages_done, int) else 0,
        "stagesTotal": stages_total,
        "examDate": exam_date_str,
        "daysUntilExam": days_until_exam,
        "estimatedPercentile": estimated_percentile,
        "progressPercent": progress_pct,
    }

    # ── 今日 vs 昨日对比（趋势变化）──
    yesterday_key = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_ds = daily_stats.get(yesterday_key, {})
    yesterday_questions = yesterday_ds.get("questionCount", 0)
    yesterday_acc_sum = yesterday_ds.get("accuracySum", 0.0)
    yesterday_avg = round(yesterday_acc_sum / yesterday_questions) if yesterday_questions > 0 else None

    # 趋势：比较今日和昨日的答题数+正确率
    rank_change = 0  # 0=持平, 1=上升, -1=下降
    if today_questions > 0 and yesterday_questions > 0:
        today_score = today_avg_score or 0
        yesterday_score = yesterday_avg or 0
        if today_score > yesterday_score + 5:
            rank_change = 1
        elif today_score < yesterday_score - 5:
            rank_change = -1
    elif today_questions > 0 and yesterday_questions == 0:
        rank_change = 1  # 昨天没学今天学了=上升

    # ── 今日学习卡片 ──
    today_card = {
        "questionsAnswered": today_questions,
        "averageScore": today_avg_score,
        "studyMinutes": analytics.get("todayStudyMinutes", 0) or 0,
        "weakPointsCount": len(weak_kps),
        "rankChange": rank_change,
        "yesterdayQuestions": yesterday_questions,
        "yesterdayScore": yesterday_avg,
    }

    return _product_response(
        {
            **analytics,
            "heatmap": heatmap,
            "weaknessRanking": weakness_ranking,
            "progressCurve": progress_curve,
            "studyCalendar": study_calendar,
            "goalTracking": goal_tracking,
            "todayCard": today_card,
            "summary": "多智能体协同学习分析仪表盘（M6）。",
        },
        session_id=session_id, subject_id=subjectId, source="agent",
    )


@router.get("/learning-events/timeline")
def learning_timeline(
    sessionId: str = "",
    subjectId: str = "",
    limit: int = 50,
    type: str = "",
    range: int = 0,
) -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    subject_id = str(subjectId).strip()
    _ensure_session_linked(session_id, subject_id=subject_id)
    if not session_id:
        return _product_response({"events": [], "total": 0}, session_id="", source="none")

    try:
        db = SessionLocal()
        from app.db.repository import get_events as repo_get_events
        raw_events = repo_get_events(db, session_id, limit=limit)
    finally:
        db.close()

    if type:
        raw_events = [e for e in raw_events if e.event_type == type]
    if range > 0:
        cutoff = time.time() - range * 86400
        raw_events = [e for e in raw_events if e.created_at and e.created_at.timestamp() >= cutoff]

    db_resources = ag_get_resources(session_id)
    resource_titles: dict[str, str] = {}
    resource_types: dict[str, str] = {}
    resource_stages: dict[str, str] = {}
    resource_chapters: dict[str, str] = {}
    for r in db_resources:
        rid = r.get("id", "")
        if rid:
            resource_titles[rid] = r.get("title", "") or ""
            resource_types[rid] = r.get("type", "") or ""
            resource_stages[rid] = r.get("related_stage_id", "") or r.get("relatedStageId", "") or ""
            resource_chapters[rid] = r.get("related_chapter", "") or r.get("relatedChapter", "") or ""

    state = conversation_store.get(session_id)
    if state and state.last_result:
        for item in state.last_result.get("resources", []):
            normalized = _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
            rid = normalized.get("id", "")
            if rid and rid not in resource_titles:
                resource_titles[rid] = normalized.get("title", "") or ""
                resource_types[rid] = normalized.get("type", "") or ""
                resource_stages[rid] = normalized.get("relatedStageId", "") or ""
                resource_chapters[rid] = normalized.get("relatedChapter", "") or ""

    EVENT_CONFIG: dict[str, dict[str, Any]] = {
        "resource_view":     {"label": "查看了资源",     "icon": "👁️", "color": "blue"},
        "resource_complete": {"label": "完成了资源",     "icon": "✅", "color": "green"},
        "quiz_result":       {"label": "提交了练习",     "icon": "📝", "color": "amber"},
        "practice_result":   {"label": "提交了实操",     "icon": "💻", "color": "cyan"},
        "feedback":          {"label": "提交了反馈",     "icon": "💬", "color": "purple"},
        "stage_complete":    {"label": "完成了阶段",     "icon": "🎯", "color": "rose"},
        "node_progress":     {"label": "学习节点更新",   "icon": "📌", "color": "gray"},
    }

    resource_kps: dict[str, list[str]] = {}
    for r in db_resources:
        rid = r.get("id", "")
        if rid:
            kps = r.get("knowledge_points") or r.get("knowledgePoints") or []
            if isinstance(kps, list):
                resource_kps[rid] = kps

    events_out: list[dict[str, Any]] = []
    for evt in raw_events:
        rid = evt.resource_id or ""
        meta = dict(evt.metadata_ or {})
        title = resource_titles.get(rid, meta.get("title", "") or "")
        rtype = resource_types.get(rid, meta.get("type", "") or "")
        stage_id = resource_stages.get(rid, meta.get("relatedStageId", meta.get("related_stage_id", "")) or "")
        chapter = resource_chapters.get(rid, meta.get("relatedChapter", meta.get("related_chapter", "")) or "")
        config = EVENT_CONFIG.get(evt.event_type, {"label": evt.event_type, "icon": "📋", "color": "gray"})

        if evt.event_type == "node_progress" and not meta.get("stageTitle") and meta.get("nodeId"):
            nid = str(meta.get("nodeId", ""))
            stage_id_part = nid.rsplit("_node_", 1)[0] if "_node_" in nid else ""
            if stage_id_part:
                try:
                    from app.services.agent_service import get_learning_path as _lp
                    path = _lp(session_id)
                    if path:
                        for stage in path.get("stages", []):
                            sid = stage.get("id", "")
                            if sid and stage_id_part in sid:
                                meta["stageTitle"] = stage.get("title", "")
                                for n in stage.get("nodes", []):
                                    if n.get("id") == nid:
                                        meta["nodeName"] = n.get("topic", "")
                                        break
                                break
                except Exception:
                    logger.warning("Failed to enrich timeline node for session %s", session_id)

        if rid and rid in resource_kps:
            meta["knowledgePoints"] = resource_kps[rid]

        events_out.append({
            "id": evt.id,
            "event": evt.event_type,
            "label": config["label"],
            "icon": config["icon"],
            "color": config["color"],
            "resourceId": rid,
            "resourceTitle": title,
            "resourceType": rtype,
            "relatedStageId": stage_id,
            "relatedChapter": chapter,
            "metadata": meta,
            "timestamp": int(evt.created_at.timestamp() * 1000) if evt.created_at else 0,
        })

    return _product_response({"events": events_out, "total": len(events_out)}, session_id=session_id, subject_id=subjectId, source="db")


# ═══════════════════════════════════════════════════════════════════════
# Question & Grading endpoints（M3+M4）
# ═══════════════════════════════════════════════════════════════════════


@router.post("/questions/generate")
def generate_questions(payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    """触发 QuestionAgent 生成试题并持久化到 DB。"""
    session_id = _payload_session_id(payload)
    subject_id = _payload_subject_id(payload)
    message = str(payload.get("message", "生成练习题"))
    _validate_message(message)
    _ensure_session_linked(session_id, subject_id=subject_id)

    conversation_store.append_message(session_id, "user", message)
    # Skip _classify_intent() here — its LLM call would be wasted since
    # we hard-code action="generate_questions" below.  Facts extraction
    # is handled by the pipeline via agent_service.run_agents().

    result = _run_agents(message, session_id=session_id, progress_callback=None,
                         agents_filter=get_agent_ids("generate_questions"))

    questions = result.get("questions", [])
    qsid = result.get("question_set_id", "")
    # 持久化到 DB
    if questions:
        try:
            db = SessionLocal()
            for q in questions:
                q["question_set_id"] = qsid
            from app.db.repository import upsert_questions
            upsert_questions(db, session_id, questions)
        finally:
            db.close()

    return _product_response({
        "questionSetId": qsid, "questions": questions, "count": len(questions),
    }, session_id=session_id, source="agent")


def _q_to_dict(q) -> dict:
    """ORM QuestionModel → dict，JSON 字段已自动反序列化。"""
    return {
        "question_id": q.question_id, "type": q.type, "stem": q.stem,
        "question_set_id": q.question_set_id,
        "options": q.options, "correct": q.correct, "explanation": q.explanation,
        "difficulty": q.difficulty, "knowledge_points": q.knowledge_points,
        "tags": q.tags, "scoring_rubric": q.scoring_rubric,
        "reference_answer": q.reference_answer, "source": q.source,
        "quality_status": q.quality_status, "created_at": str(q.created_at) if q.created_at else None,
    }


@router.get("/questions")
def list_questions(sessionId: str = "", subjectId: str = "",
                   knowledgePoint: str = "", difficulty: str = "",
                   qtype: str = "") -> dict[str, Any]:
    """查询已有试题列表（从 DB）。"""
    session_id = _resolve_session_id(sessionId, subjectId)
    _ensure_session_linked(session_id, subject_id=subjectId)
    try:
        db = SessionLocal()
        from app.db.repository import get_questions as repo_get_questions
        rows = repo_get_questions(db, session_id, knowledge_point=knowledgePoint,
                                  difficulty=difficulty, qtype=qtype)
        # 隐藏答案
        safe = [{k: v for k, v in _q_to_dict(r).items()
                 if k not in ("correct", "explanation", "scoring_rubric", "reference_answer")}
                for r in rows]
        return _product_response({"questions": safe, "count": len(safe)}, session_id=session_id, source="db")
    finally:
        db.close()


@router.get("/questions/sets")
def question_sets(sessionId: str = "") -> dict[str, Any]:
    """列出所有题目集（按 question_set_id 分组）。"""
    session_id = _resolve_session_id(sessionId, "")
    try:
        db = SessionLocal()
        from app.db.repository import get_questions as repo_get_questions
        all_qs = repo_get_questions(db, session_id, limit=500)

        # 按 question_set_id 分组
        sets: dict[str, dict] = {}
        for q in all_qs:
            qsid = q.question_set_id or "default"
            if qsid not in sets:
                sets[qsid] = {"questionSetId": qsid, "title": qsid, "questions": [], "count": 0, "completed": 0}
            sets[qsid]["questions"].append(q)
            sets[qsid]["count"] += 1

        # 统计完成数（有判卷记录的算完成）
        from app.db.repository import get_answer_history
        records = get_answer_history(db, session_id, limit=500)
        graded_ids = {r.question_id for r in records}

        result = []
        for qsid, data in sets.items():
            qs = data["questions"]
            completed = sum(1 for q in qs if q.question_id in graded_ids)
            # 取第一个题目的前几个字作标题
            title = qs[0].stem[:30] + ("…" if len(qs[0].stem) > 30 else "") if qs else qsid
            knowledge_points = list(set(
                kp for q in qs if isinstance(q.knowledge_points, list)
                for kp in q.knowledge_points
            ))[:5]
            result.append({
                "questionSetId": qsid,
                "title": title,
                "knowledgePoints": knowledge_points,
                "count": len(qs),
                "completed": completed,
                "createdAt": int(qs[0].created_at.timestamp() * 1000) if qs and qs[0].created_at else 0,
            })

        return _product_response({"sets": result}, session_id=session_id, source="db")
    finally:
        db.close()


@router.delete("/questions/sets/{set_id}")
def delete_question_set(set_id: str, sessionId: str = "") -> dict[str, Any]:
    """删除一个题目集及其所有题目和答题记录。"""
    session_id = _resolve_session_id(sessionId, "")
    db = SessionLocal()
    try:
        from app.db.repository import get_questions as repo_get_questions, get_answer_history
        # Find all questions in this set
        qs = [q for q in repo_get_questions(db, session_id, limit=500) if q.question_set_id == set_id]
        if not qs:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="题目集不存在")
        qids = [q.question_id for q in qs]
        # Delete answer records for these questions
        db.query(AnswerRecordModel).filter(AnswerRecordModel.question_id.in_(qids)).delete(synchronize_session=False)
        # Delete practice questions
        db.query(PracticeQuestionModel).filter(PracticeQuestionModel.question_id.in_(qids)).delete(synchronize_session=False)
        db.commit()
        return {"status": "success", "data": {"deleted": True, "count": len(qids)}}
    finally:
        db.close()


@router.get("/questions/weak")
def weak_questions(sessionId: str = "", errorType: str = "", limit: int = 20) -> dict[str, Any]:
    """错题本：查询作答错误的题目及判卷结果。"""
    session_id = _resolve_session_id(sessionId, "")
    try:
        db = SessionLocal()
        from app.db.repository import get_weak_records, get_question_by_id
        records = get_weak_records(db, session_id, error_type=errorType, limit=limit)
        data = []
        for r in records:
            q = get_question_by_id(db, r.question_id, session_id)
            data.append({
                "question": _q_to_dict(q) if q else None,
                "last_answer": r.student_answer,
                "grading_result": {
                    "total_score": r.total_score, "dimension_scores": r.dimension_scores,
                    "dimension_feedback": r.dimension_feedback, "error_type": r.error_type,
                    "error_label": r.error_label, "error_explanation": r.error_explanation,
                    "error_action": r.error_action, "suggestions": r.suggestions,
                    "strengths": r.strengths,
                },
                "attempted_at": int(r.created_at.timestamp() * 1000) if r.created_at else 0,
            })
        return _product_response({"records": data, "total": len(data)}, session_id=session_id, source="db")
    finally:
        db.close()


@router.get("/questions/history")
def answer_history(sessionId: str = "", limit: int = 50) -> dict[str, Any]:
    """答题历史：查询所有作答记录及统计。"""
    session_id = _resolve_session_id(sessionId, "")
    try:
        db = SessionLocal()
        from app.db.repository import get_answer_history, get_answer_stats, get_question_by_id
        records = get_answer_history(db, session_id, limit=limit)
        stats = get_answer_stats(db, session_id)
        data = []
        for r in records:
            q = get_question_by_id(db, r.question_id, session_id)
            data.append({
                "question_id": r.question_id,
                "question": _q_to_dict(q) if q else None,
                "answer": r.student_answer,
                "grading_result": {
                    "total_score": r.total_score, "dimension_scores": r.dimension_scores,
                    "dimension_feedback": r.dimension_feedback, "error_type": r.error_type,
                    "error_label": r.error_label,
                },
                "created_at": int(r.created_at.timestamp() * 1000) if r.created_at else 0,
            })
        return _product_response({
            "records": data, "totalCorrect": stats["totalCorrect"],
            "totalAttempted": stats["totalAttempted"],
        }, session_id=session_id, source="db")
    finally:
        db.close()


@router.get("/questions/{question_id}")
def get_question(question_id: str, sessionId: str = "", reveal: bool = False) -> dict[str, Any]:
    """获取单题详情（从 DB）。reveal=True 时返回答案。"""
    session_id = _resolve_session_id(sessionId, "")
    try:
        db = SessionLocal()
        from app.db.repository import get_question_by_id as repo_get_q
        q = repo_get_q(db, question_id, session_id)
        if not q:
            return _product_response(None, session_id=session_id, status="error", message="题目不存在", source="db")
        data = _q_to_dict(q)
        if not reveal:
            for k in ("correct", "explanation", "scoring_rubric", "reference_answer"):
                data.pop(k, None)
        return _product_response({"question": data}, session_id=session_id, source="db")
    finally:
        db.close()


@router.post("/questions/{question_id}/grade")
def grade_answer(question_id: str, payload: dict[str, Any], auth: AuthContext = Depends(reject_parent)) -> dict[str, Any]:
    """提交作答，触发 GradingAgent 判卷并持久化到 DB。"""
    session_id = _payload_session_id(payload)
    student_answer = str(payload.get("answer", "")).strip()
    if not student_answer:
        return _product_response(None, session_id=session_id, status="error",
                                 message="作答不能为空", source="agent")

    # 从 DB 查题目
    try:
        db = SessionLocal()
        from app.db.repository import get_question_by_id as repo_get_q
        q = repo_get_q(db, question_id, session_id)
        if not q:
            return _product_response(None, session_id=session_id, status="error",
                                     message="题目不存在", source="db")
        question = _q_to_dict(q)
    finally:
        db.close()

    from app.agents.grading_agent import GradingAgent
    agent = GradingAgent(mock_data={}, llm_client=_llm_client())
    grading_result = agent.run({
        "session_id": session_id, "question": question,
        "student_answer": student_answer,
        "profile_facts": {"_raw_user_message": student_answer},
    })
    result_data = grading_result.get("grading_result", {})

    # 持久化作答记录
    if isinstance(result_data, dict):
        try:
            db = SessionLocal()
            from app.db.repository import save_answer_record
            save_answer_record(db, {
                "session_id": session_id, "question_id": question_id,
                "student_answer": student_answer,
                **result_data,
            })
        finally:
            db.close()

    return _product_response({"gradingResult": result_data}, session_id=session_id, source="agent")


# ═══════════════════════════════════════════════════════════════════════════
# Section lecture endpoints
# ═══════════════════════════════════════════════════════════════════════════


def _inject_spark_images(md: str, section_title: str) -> str:
    """为讲义中每个 ## 主章节标题下插入星火生成的配图。

    只生成前 3 张图片以避免耗时过长，每张图片用 base64 嵌入。
    如果 Spark 未配置或生成失败，跳过不影响讲义正文。
    """
    import re as _re_img
    try:
        from app.services.spark_provider import generate_image
    except Exception:
        return md

    # 找到所有 ## 标题位置
    headings = list(_re_img.finditer(r'^## (.+)$', md, _re_img.MULTILINE))
    if not headings:
        return md

    parts: list[str] = []
    last_end = 0
    img_count = 0
    max_images = 3

    for m in headings:
        if img_count >= max_images:
            break
        title = m.group(1).strip()
        # 标题前的文本
        parts.append(md[last_end:m.end()])
        last_end = m.end()

        # 生成配图
        try:
            result = generate_image(
                f"教育插图：{section_title} - {title}。简洁清晰的图解风格，适合教材配图。",
                width=1024, height=768,
            )
            if result.get("status") == "success" and result.get("image_base64"):
                img_md = f'\n\n![{title}](data:image/png;base64,{result["image_base64"]})\n\n'
                parts.append(img_md)
                img_count += 1
                logger.info("Spark image generated for section: %s", title)
        except Exception as e:
            logger.debug("Spark image failed for %s: %s", title, e)

    # 剩余内容
    parts.append(md[last_end:])
    return "".join(parts)


def _clean_markdown(md: str) -> str:
    """Clean common LLM-generated markdown formatting issues."""
    import re

    # 暴力修复表格粘连
    # 把 |---|...|---| 这样的分隔行拎出来独立一行
    def _fix_table_line(line: str) -> str:
        m = re.search(r'((?:\|[-:]{3,})+\|)', line)
        if not m:
            return line
        sep = m.group(0)
        before = line[:m.start()].strip().rstrip('|').strip()
        after = line[m.end():].strip()
        # 表头
        result = [before + ' |'] if before else []
        result.append(sep)
        # 数据行：按 | 拆，数分隔行的竖线数 = 列数+1
        col_count = sep.count('|') - 1
        if col_count < 1:
            col_count = 2
        cells = [c.strip() for c in after.split('|') if c.strip() and not re.match(r'^[-:]+$', c.strip())]
        for i in range(0, len(cells), col_count):
            row = cells[i:i+col_count]
            if row:
                result.append('| ' + ' | '.join(row) + ' |')
        return '\n'.join(result)

    lines = md.split('\n')
    md = '\n'.join(_fix_table_line(l) for l in lines)

    lines = md.split("\n")
    fixed: list[str] = []
    for line in lines:
        # 找表格分隔行 |---|...|---|
        sep_match = re.search(r'(\|[-: ]{3,})+\|', line)
        if not sep_match:
            fixed.append(line)
            continue

        # 分隔行位置
        sep = sep_match.group(0)
        pos = sep_match.start()
        header_part = line[:pos].strip().rstrip("|").strip()
        rows_part = line[pos + len(sep):].strip()

        # 表头行
        if header_part:
            # 确保以 | 开头结尾
            if not header_part.startswith("|"):
                header_part = "| " + header_part
            if not header_part.endswith("|"):
                header_part = header_part + " |"
            fixed.append(header_part)

        # 分隔行
        fixed.append(sep)

        # 数据行：按 | 拆分，数表头列数重组
        col_count = header_part.count("|") - 1 if header_part else sep.count("|") - 1
        if col_count < 1:
            col_count = 2
        cells = [c.strip() for c in rows_part.split("|") if c.strip()]
        for i in range(0, len(cells), col_count):
            row_cells = cells[i:i + col_count]
            if row_cells:
                fixed.append("| " + " | ".join(row_cells) + " |")

    # 清洗空表头
    cleaned: list[str] = []
    for line in fixed:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            if all(re.match(r'^[-:\s]+$', c) for c in cells if c):
                cleaned.append(stripped)
                continue
            filled = [c if c else "(项目)" for c in cells]
            cleaned.append("| " + " | ".join(filled) + " |")
        else:
            cleaned.append(stripped)
    return "\n".join(cleaned)


_PROFILE_KEYS = {
    "major_background", "knowledge_base", "learning_goal", "cognitive_style",
    "error_patterns", "coding_ability", "learning_progress", "interest_direction",
    "learning_rhythm",
}
_LECTURE_HEADINGS = ("学习目标", "核心概念", "示例", "易错点", "小结")


def _is_profile_json(content: str) -> bool:
    try:
        value = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and len(_PROFILE_KEYS.intersection(value)) >= 3


def _is_valid_section_lecture(content: str, section_title: str, knowledge_points: list[Any]) -> bool:
    text = str(content or "").strip()
    if len(text) < 120 or _is_profile_json(text):
        return False
    point_names = [str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in knowledge_points]
    has_subject = section_title in text or any(name and name in text for name in point_names)
    return has_subject and sum(heading in text for heading in _LECTURE_HEADINGS) >= 2


def _fallback_section_lecture(section_title: str, section_goal: str, knowledge_points: list[Any]) -> str:
    points = [str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in knowledge_points]
    topic = "、".join(point for point in points if point) or section_title
    goal = section_goal or f"理解{topic}的核心概念和基本应用。"
    return f"""# {section_title}

## 学习目标
- {goal}
- 能说明{topic}在数据结构学习中的作用。

## 核心概念
{topic}需要结合定义、操作成本和适用场景理解。学习时先区分概念之间的联系，再用具体操作验证结论。

## 示例
以顺序访问和插入操作为例，比较不同数据结构在时间复杂度和存储方式上的差异，并说明选择依据。

## 易错点
- 不要只记结论，要说明操作发生在什么位置。
- 不要混淆访问、查找、插入和删除的成本。

## 小结
本节围绕{topic}建立基础认识。完成阅读后，建议结合一道练习题验证对操作复杂度和结构特点的理解。"""


@router.get("/sections/{section_id}/lecture")
def get_section_lecture(section_id: str, sessionId: str = "") -> dict[str, Any]:
    """Read existing lecture for a section. Returns None if not generated yet."""
    try:
        db = SessionLocal()
        query = db.query(ResourceModel).filter(
            ResourceModel.related_section_id == section_id,
            ResourceModel.type == "lecture",
        )
        if sessionId:
            query = query.filter(ResourceModel.session_id == sessionId)
        lecture = query.order_by(ResourceModel.created_at.desc()).first()

        if lecture and not _is_profile_json(lecture.content or ""):
            data = {
                "id": lecture.id,
                "title": lecture.title or "",
                "content": lecture.content or "",
                "sectionId": lecture.related_section_id or "",
                "chapterId": lecture.related_chapter_id or "",
                "stageId": lecture.related_stage_id or "",
                "createdAt": int(lecture.created_at.timestamp() * 1000) if lecture.created_at else 0,
            }
            return _product_response({"lecture": data}, session_id=sessionId or (lecture.session_id or ""), source="db")
        return _product_response({"lecture": None}, session_id=sessionId or "", source="db")
    finally:
        db.close()


@router.post("/sections/{section_id}/lecture/generate")
def generate_section_lecture(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a structured lecture for a section using LLM, persist as Resource."""
    session_id = _payload_session_id(payload)
    section_title = str(payload.get("sectionTitle", "")).strip()
    section_goal = str(payload.get("sectionGoal", "")).strip()
    chapter_id = str(payload.get("chapterId", "")).strip()
    stage_id = str(payload.get("stageId", "")).strip()
    path_id = str(payload.get("pathId", "")).strip()
    knowledge_points = payload.get("knowledgePoints", [])
    resource_type = str(payload.get("type", "lecture")).strip()
    requirements = str(payload.get("requirements", "")).strip()

    if not section_title:
        return _product_response(None, session_id=session_id, status="error", message="sectionTitle required", source="agent")

    # Build knowledge point list for prompt
    kp_lines = ""
    if isinstance(knowledge_points, list) and knowledge_points:
        kp_lines = "\n".join(f"- {kp.get('name', kp) if isinstance(kp, dict) else str(kp)}" for kp in knowledge_points[:10])

    if resource_type == "reading":
        lecture_excerpt = str(payload.get("lectureContent", "")).strip()
        lecture_ctx = f"\n\n## 本节讲义内容（供参考，请基于此拓展）\n{lecture_excerpt}" if lecture_excerpt else ""
        prompt = f"""你是一位资深教育专家，请基于以下讲义内容为「{section_title}」编写一份拓展阅读材料。

要求：
1. 深入挖掘讲义中涉及但未展开的背景知识、历史渊源
2. 提供与本节知识点相关的实际工业/科研应用案例（至少2个）
3. 介绍进阶话题和学习路径，引导学有余力的学生进一步探索
4. 推荐3-5本经典书籍或论文，附简短推荐理由
5. 每个案例/话题至少写150字，总字数800字以上
6. 内容必须与讲义紧密相关，切忌泛泛而谈

Markdown格式，结构清晰，用小标题组织。{lecture_ctx}"""
    elif resource_type == "practice":
        lecture_excerpt = str(payload.get("lectureContent", "")).strip()
        lecture_ctx = f"\n\n## 本节讲义内容（供参考，请基于此设计案例）\n{lecture_excerpt}" if lecture_excerpt else ""
        prompt = f"""你是一位资深编程导师，请基于以下讲义内容为「{section_title}」编写一份实操案例。

要求：
1. 设计与讲义知识点紧密对应的编程练习（至少2个独立案例）
2. 每个案例包含：场景描述、完整可运行代码、详细注释、输入输出示例
3. 指出常见错误和解决方案
4. 代码要能真正运行，不要留空占位符（如 # TODO）
5. 每个案例至少200字说明 + 完整代码

Markdown格式，代码用```包裹并标注语言。{lecture_ctx}"""
    else:
        prompt = f"""你是一位资深大学教师，请为小节「{section_title}」编写一份达到正式出版教材水准的讲义。

学习目标：{section_goal or '掌握本节知识点'}

{f"本节涵盖以下知识点：{chr(10)}{kp_lines}" if kp_lines else ""}

教材级讲义要求：
- 概念解释要有"为什么"而不只是"是什么"——讲清楚来龙去脉、设计动机、底层原理，每个概念至少写200字
- 每个抽象概念配一个具体实例帮助理解
- 数学公式用 LaTeX（$...$ 或 $$...$$）呈现，重要公式单独成行
- 复杂流程用 ```mermaid 图可视化
- > 引用块用于标注重点、注意事项和常见误区
- 代码示例完整可运行，有输入输出演示
- 表格每行必须独占一行（表头/分隔行/数据行各一行），禁止把多行表格挤在一行里
- 正文段落至少2-3句，禁止用空泛的一句话敷衍

输出结构（按顺序）：

## 学习目标
列出 3-5 个具体可衡量的目标

## 前置知识
| 概念 | 要求 | 与本节关联 |
|---|---|---|
| ... | ... | ... |
（至少 3 行）

## 知识结构图
```mermaid 绘制 mindmap，覆盖本节所有概念及其关系

## 核心概念详解
每个概念用 ### 子标题独立成节：
- 为什么需要这个概念（动机/背景）
- 原理阐述（配 LaTeX 公式）
- 具体实例
- > 重点提示

## 代码实践
完整可运行代码（```python），详细注释 + 运行结果

## 常见误区
> 用引用块逐一列出，每个错误写明为什么错 + 正确做法

## 本节总结
| 关键词 | 解释 |
|---|---|
| ... | ... |
（至少 5 行） + 一段总结段落

格式要求：
- **表格每行独占一行，禁止把多行挤在一行**
- Mermaid mindmap 用 root((主题))，子节点缩进；graph LR 节点 ID 用英文
- 代码块指定语言
- 重点用 > 引用块
- 直接输出 Markdown

表格正确格式（注意每行独立）：
| 概念 | 说明 | 示例 |
|---|---|---|
| 缓存 | 高速小容量存储器 | CPU 三级缓存 |
| 寄存器 | CPU 内部最快存储 | 通用寄存器 |

Mermaid 示例(必须严格照此格式，用 ```mermaid 包裹，flowchart LR 语法):
```mermaid
flowchart LR
  A[核心主题] --> B[子概念1]
  A --> C[子概念2]
  B --> D[细节A]
  C --> E[细节B]
```
铁律:
- 必须用 ```mermaid 和 ``` 包裹
- 只用 flowchart LR, 从左到右布局, 禁止 TD/TB/mindmap
- 节点 ID 英文字母+数字, 标签中文放[方括号]
- 禁止中文节点 ID
- 禁止 root/::id1/::icon 等语法"""

    # 从知识库获取课程内容作为上下文
    kb_context = ""
    course_name = str(payload.get("courseId", "")).strip()
    chapter_id_in = str(payload.get("chapterId", "")).strip()
    if course_name:
        try:
            from app.services.course_catalog import course_catalog
            course = course_catalog.match_course(course_name)
            if not course:
                course = course_catalog.get_course(course_name)
            if course:
                course_id = str(course.get("course_id", ""))
                catalog_chapters = course.get("chapters", [])
                # 尝试匹配章节：按索引或标题模糊匹配
                chapter_content = ""
                chapter_order = 0
                # 从 chapterId 提取索引（如 path_xxx_s0_ch1 → order=1）
                import re as _re
                idx_match = _re.search(r'ch(\d+)', chapter_id_in)
                if idx_match:
                    chapter_order = int(idx_match.group(1))
                if catalog_chapters and chapter_order < len(catalog_chapters):
                    ch = catalog_chapters[chapter_order]
                    ch_loaded = course_catalog.load_chapter(course_id, str(ch.get("chapter_id", "")))
                    if ch_loaded and ch_loaded.get("content"):
                        chapter_content = ch_loaded["content"]  # 完整教材内容

                chapter_names = "\n".join(f"- 第{i+1}章：{ch.get('title', '')}" for i, ch in enumerate(catalog_chapters[:8]))
                if chapter_names:
                    kb_context = f"\n\n本课程章节结构：\n{chapter_names}"
                if chapter_content:
                    kb_context += f"\n\n当前章节的参考教材内容（可参考其中的概念和深度，但用自己的话重新组织）：\n{chapter_content}"
        except Exception:
            pass

    # ── 用户定制需求 ──
    req_context = f"\n\n## 学生特殊要求（必须严格遵循，优先级最高）\n{requirements}" if requirements else ""

    client = _llm_client()
    try:
        raw = client.chat(
            messages=[{"role": "user", "content": prompt + kb_context + req_context}],
            temperature=0.3, max_tokens=settings.lecture_max_tokens,
        )
    except Exception as e:
        logger.warning("Lecture generation failed for section %s: %s", section_id, e)
        return _product_response(None, session_id=session_id, status="error", message=f"生成失败: {e}", source="agent")

    # 后处理：切开场白
    if raw.startswith("好的") or raw.startswith("作为"):
        raw = re.sub(r"^[^\n#]*?\n", "", raw, count=1)
    raw = raw.lstrip("\n")
    # 后处理：裸 mermaid 语法补包裹
    if "```mermaid" not in raw:
        if re.search(r"^\s*(graph |mindmap|flowchart )", raw, re.MULTILINE):
            raw = re.sub(r"(^\s*(graph |mindmap|flowchart ))",
                         r"```mermaid\n\1", raw, flags=re.MULTILINE) + "\n```\n"
        elif re.search(r"^\s*root", raw, re.MULTILINE):
            raw = re.sub(r"(^\s*root)", r"```mermaid\nmindmap\n\1",
                         raw, flags=re.MULTILINE) + "\n```\n"
    # 后处理：清洗空表头等常见格式问题
    raw = _clean_markdown(raw)
    if not _is_valid_section_lecture(raw, section_title, knowledge_points if isinstance(knowledge_points, list) else []):
        logger.warning("Rejected invalid lecture output for section %s; using deterministic fallback", section_id)
        raw = _fallback_section_lecture(
            section_title,
            section_goal,
            knowledge_points if isinstance(knowledge_points, list) else [],
        )

    # 图文并茂：为每个 ## 主章节生成星火配图
    raw = _inject_spark_images(raw, section_title)

    # Persist as Resource
    resource_id = f"lecture_{section_id}"
    try:
        db = SessionLocal()
        from app.db.repository import upsert_resource
        upsert_resource(db, session_id, {
            "id": resource_id,
            "type": "lecture",
            "title": f"讲义：{section_title}",
            "description": section_goal or "",
            "content": raw,
            "format": "text",
            "difficulty": "medium",
            "estimated_minutes": 30,
            "source": "agent_generated",
            "related_stage_id": stage_id,
            "related_chapter_id": chapter_id,
            "related_section_id": section_id,
            "knowledge_points": [kp.get("name", str(kp)) if isinstance(kp, dict) else str(kp) for kp in (knowledge_points or [])],
        })
    finally:
        db.close()

    lecture_data = {
        "id": resource_id,
        "title": f"讲义：{section_title}",
        "content": raw,
        "sectionId": section_id,
        "chapterId": chapter_id,
        "stageId": stage_id,
        "createdAt": int(time.time() * 1000),
    }
    return _product_response({"lecture": lecture_data}, session_id=session_id, source="agent")


# ═══════════════════════════════════════════════════════════════════════════
# 智能辅导端点
# ═══════════════════════════════════════════════════════════════════════════

def _is_invalid_tutor_reply(reply: Any) -> bool:
    text = str(reply or "").strip()
    return len(text) < 20 or _is_profile_json(text) or any(key in text for key in _PROFILE_KEYS)


def _fallback_tutor_reply(
    action_type: str,
    section_title: str,
    section_goal: str,
    knowledge_points: list[Any],
    lecture_excerpt: str,
    question: str,
) -> str:
    points = [str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in knowledge_points]
    topic = "、".join(point for point in points if point) or section_title
    action = action_type.lower()
    if not action:
        action = "diagram" if any(word in question for word in ("图", "结构", "关系")) else "concept_explanation"
    excerpt = re.sub(r"\s+", " ", lecture_excerpt).strip()[:180]
    context = f"本节目标是{section_goal or f'理解{topic}'}。"
    if action in {"diagram", "structure"}:
        return f"""## {section_title} 的知识结构

```mermaid
mindmap
  root(({topic}))
    核心定义
    典型操作
    时间复杂度
    常见误区
```

{context}先理解核心定义，再比较典型操作的成本，最后通过练习检验掌握情况。"""
    if action in {"example", "exercise"}:
        return f"""## {section_title} 示例

以{topic}为例，先写出操作目标，再分别分析访问、查找、插入和删除时需要移动或访问的数据量。比较结果时要说明操作位置和数据规模。

> 练习：选择一个具体操作，写出你的判断依据，而不只写结论。"""
    if action == "simplify":
        return f"""## {section_title} 的简单解释

把{topic}看成解决“怎样存放和处理数据”的不同工具。先记住每种工具最擅长的操作，再通过一个小例子比较它们的差异。{context}"""
    if action == "summarize":
        return f"""## {section_title} 小结

- 本节围绕{topic}建立基础概念。
- 重点是把操作过程和时间复杂度对应起来。
- 下一步用一道具体练习验证理解。"""
    if action == "common_mistakes":
        return f"""## {section_title} 常见错误

- 只背复杂度结论，没有说明操作位置。
- 混淆访问、查找、插入和删除。
- 忽略数据规模变化对操作成本的影响。"""
    detail = f"讲义当前重点：{excerpt}" if excerpt else context
    return f"""## {section_title} 概念讲解

{topic}需要从定义、操作方式和适用场景三个角度理解。先明确数据如何组织，再分析每种操作需要访问或移动多少数据。

{detail}

> 学习时请把每个结论和一个具体操作对应起来。"""


def _public_tutor_video(result: dict[str, Any]) -> dict[str, Any]:
    raw_status = str(result.get("status") or "failed")
    script = str(result.get("script") or "").strip()
    if raw_status in {"success", "script_ready"}:
        status, message = "completed", "讲解视频脚本已准备好。"
    elif raw_status in {"provider_not_configured", "script_ready_provider_not_configured"}:
        status = "provider_not_configured"
        message = "视频暂不能生成，但脚本已准备好。" if script else "讲解视频服务暂未配置，当前可以先查看或生成视频脚本。"
    else:
        status, message = "generation_failed", "讲解视频生成失败，请稍后重试。"
    return {
        "status": status,
        "provider": str(result.get("provider") or "spark_video"),
        "script": script,
        "userMessage": message,
        "metadata": {"raw_status": raw_status},
    }


@router.post("/sections/{section_id}/generate-all")
def generate_all_section_resources(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Multi-agent pipeline: profile → knowledge → resource for a section."""
    session_id = _payload_session_id(payload)
    section_title = str(payload.get("sectionTitle", "")).strip()
    section_goal = str(payload.get("sectionGoal", "")).strip()
    chapter_id = str(payload.get("chapterId", "")).strip()
    stage_id = str(payload.get("stageId", "")).strip()
    kps = payload.get("knowledgePoints", [])
    kp_names = [kp.get("name", str(kp)) if isinstance(kp, dict) else str(kp) for kp in (kps or [])[:8]]
    requirements = str(payload.get("requirements", "")).strip()

    if not session_id or not section_title:
        return _product_response(None, session_id=session_id, status="error", message="sessionId and sectionTitle required", source="agent")

    state_obj = conversation_store.get(session_id)
    results: dict[str, Any] = {"agents_run": [], "resources": []}

    # ── Agent 1: Profile ──
    try:
        from app.agents.base import get_agent_class
        pa = get_agent_class("profile_agent")(llm_client=_llm_client())
        pr = pa.run({"profile_facts": dict(state_obj.facts), "user_message": f"分析学习{section_title}的背景", "session_id": session_id})
        results["profile"] = pr.get("profile", {})
        results["agents_run"].append("profile_agent")
    except Exception as e:
        logger.warning("ProfileAgent failed: %s", e)

    # ── Agent 2: Knowledge ──
    try:
        ka = get_agent_class("knowledge_agent")(llm_client=_llm_client())
        kr = ka.run({"profile_facts": dict(state_obj.facts), "user_message": f"检索{section_title}相关知识", "session_id": session_id, "knowledge_points": kp_names})
        results["knowledge"] = kr.get("knowledge_context", {})
        results["agents_run"].append("knowledge_agent")
    except Exception as e:
        logger.warning("KnowledgeAgent failed: %s", e)

    # ── Agent 3: Resource (receives profile + knowledge) ──
    try:
        ra = get_agent_class("resource_agent")(llm_client=_llm_client())
        resource_ctx = {
            "session_id": session_id,
            "profile_facts": dict(state_obj.facts),
            "profile": results.get("profile", {}),
            "knowledge_context": results.get("knowledge", {}),
            "learning_path": [{"stage_id": stage_id or section_id, "title": section_title,
                "chapters": [{"chapter_id": chapter_id or section_id, "title": section_title,
                    "sections": [{"section_id": section_id, "title": section_title, "goal": section_goal,
                        "knowledge_points": [{"name": n} for n in kp_names]}]}]}],
            "path_mode": "textbook",
        }
        if requirements:
            resource_ctx["user_message"] = f"生成资源时遵循学生要求：{requirements}"
        rr = ra.run(resource_ctx)
        results["resources"] = rr.get("resources", [])
        results["agents_run"].append("resource_agent")
    except Exception as e:
        logger.warning("ResourceAgent failed: %s", e)

    # ── Agent 4: QuestionAgent (quiz) ──
    try:
        qa = get_agent_class("question_agent")(llm_client=_llm_client())
        qa_msg = f"为{section_title}生成3-5道练习题，知识点：{', '.join(kp_names)}"
        if requirements:
            qa_msg += f"。学生特殊要求：{requirements}"
        qr = qa.run({
            "session_id": session_id,
            "profile_facts": dict(state_obj.facts),
            "user_message": qa_msg,
            "course": {"chapters": [{"title": section_title, "knowledge_points": kp_names}]},
            "diagnosis": {"weak_knowledge_points": [
                {"name": n, "priority": "medium"} for n in kp_names[:3]
            ]},
        })
        questions = qr.get("questions", [])
        if questions:
            results["quiz_questions"] = questions
            results["agents_run"].append("question_agent")
    except Exception as e:
        logger.warning("QuestionAgent failed: %s", e)

    # ── Agent 5: Video via DeepTutor ──
    try:
        from app.services.deeptutor_client import generate_video_script
        video_script = generate_video_script(f"{section_title}: {section_goal}")
        if video_script and len(video_script) > 50:
            import uuid as _uuid
            results["resources"].append({
                "resource_id": _uuid.uuid4().hex[:12],
                "type": "video", "title": f"{section_title} - 教学视频脚本",
                "content": video_script, "format": "text", "difficulty": "medium",
                "source": "deeptutor", "quality_status": "passed",
            })
            results["agents_run"].append("video_generation")
    except Exception as e:
        logger.warning("Video generation failed: %s", e)

    # ── Persist ──
    try:
        db = SessionLocal()
        from app.db.repository import upsert_resource
        for r in results.get("resources", []):
            upsert_resource(db, session_id, {
                "id": r.get("resource_id", f"res_{hash(r.get('title',''))}"),
                "type": r.get("type", "lecture"), "title": r.get("title", ""),
                "description": r.get("description", ""), "content": r.get("content", ""),
                "format": r.get("format", "text"), "difficulty": r.get("difficulty", "medium"),
                "source": "agent_generated",
                "related_stage_id": stage_id, "related_chapter_id": chapter_id, "related_section_id": section_id,
            })
        db.commit()
    except Exception:
        pass
    finally:
        db.close()

    lecture_content = next((r.get("content", "") for r in results.get("resources", []) if r.get("type") == "lecture"), "")
    return _product_response({
        "agents_run": results["agents_run"],
        "resource_count": len(results.get("resources", [])),
        "lecture_content": lecture_content,
    }, session_id=session_id, source="multi_agent")


@router.post("/sections/{section_id}/tutor/ask")
def tutor_ask(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """智辅问答：注入学生画像 + 诊断数据，返回 Markdown 格式回答。"""
    session_id = _payload_session_id(payload)
    question = str(payload.get("question", "")).strip()
    quoted = str(payload.get("quoted", "") or "").strip()
    section_title = str(payload.get("sectionTitle", "")).strip()
    section_goal = str(payload.get("sectionGoal", "")).strip()
    knowledge_points = payload.get("knowledgePoints", [])
    lecture_excerpt = str(payload.get("lectureExcerpt", ""))[:1000]
    action_type = str(payload.get("actionType") or payload.get("action_type") or "").strip()

    # Combine quoted text into question if provided
    if quoted and not question:
        question = f'"""{quoted}"""\n请解释以上选中的内容'
    elif quoted and question:
        question = f'"""{quoted}"""\n{question}'

    if not question:
        return _product_response(None, session_id=session_id, status="error", message="question required", source="agent")

    # 获取学生画像
    profile_text = ""
    try:
        from app.services.agent_service import get_profile, get_analytics
        p = get_profile(session_id)
        if p:
            dims = p.get("dimensions", [])
            weaknesses = p.get("weaknesses", [])
            if dims:
                profile_text += "学生画像：\n" + "\n".join(
                    f"- {d.get('label', d.get('key',''))}: {d.get('description', d.get('value',''))}"
                    for d in dims[:5] if d.get("description") or d.get("value")
                )
            if weaknesses:
                profile_text += "\n薄弱点：\n" + "\n".join(
                    f"- {w.get('topic','')}: {w.get('reason','')}" for w in weaknesses[:3]
                )
        # 学习分析
        analytics = get_analytics(session_id) or {}
        if analytics.get("quizAccuracy") is not None:
            profile_text += f"\n练习正确率：{analytics['quizAccuracy']}%"
        if analytics.get("totalStudyMinutes"):
            profile_text += f"\n累计学习：{analytics['totalStudyMinutes']}分钟"
    except Exception:
        pass

    kp_names = ", ".join(kp.get("name", str(kp)) if isinstance(kp, dict) else str(kp) for kp in (knowledge_points or [])[:8])

    # ── Detect tutoring mode from student's course ──
    tutor_persona = "你是 EduAgent 智能助教，请为学生解答问题。"
    try:
        state = conversation_store.get(session_id)
        course = str(state.facts.get("target_course", "")).strip()
        if any(w in course for w in ["英语","日语","韩语","法语","德语","语言","雅思","托福"]):
            tutor_persona = (
                "你是 EduAgent 语言导师。你的角色是语言陪练——"
                "用目标语言与学生互动，纠正语法和发音，提供地道表达。"
                "初级学生用中英双语解释，中高级学生尽量用目标语言回复。"
                "回答中给出例句和用法说明。"
            )
        elif any(w in course for w in ["Python","Java","C++","编程","前端","后端","开发"]):
            tutor_persona = (
                "你是 EduAgent 编程导师。你的角色是帮助理解概念和调试代码。"
                "用实际代码示例讲解，解释为什么这样写而不是那样写。"
                "鼓励学生先思考再给答案，用引导式提问帮助理解。"
            )
    except Exception:
        pass

    # ── Extract quoted/selected text early ──
    sel_match = re.search(r'"""\s*\n?(.+?)\n?\s*"""', question, re.DOTALL)
    selected_excerpt = sel_match.group(1).strip()[:800] if sel_match else ""

    # ── Route to DeepTutor capabilities for specific action types ──
    if action_type in ("explain", "concept_explanation"):
        try:
            from app.services.deeptutor_client import deeptutor_call
            raw = deeptutor_call("deep_solve", question)
            if raw and len(raw) > 30:
                return {"status": "success", "data": {"reply": raw, "content_type": "tutor_explain"}}
        except Exception:
            pass
    if action_type in ("diagram", "visualize"):
        try:
            from app.services.deeptutor_client import deeptutor_call
            raw = deeptutor_call("visualize", question, config_overrides={"render_mode": "mermaid"})
            if raw and len(raw) > 30:
                return {"status": "success", "data": {"reply": raw, "content_type": "diagram"}}
        except Exception:
            pass
    if action_type == "quiz":
        try:
            from app.services.deeptutor_client import deeptutor_call
            raw = deeptutor_call("deep_question", question, config_overrides={"mode": "custom", "topic": selected_excerpt or question or section_title, "num_questions": 3})
            if raw and len(raw) > 30:
                return {"status": "success", "data": {"reply": raw, "content_type": "quiz"}}
        except Exception:
            pass

    # ── Handle video action: use DeepTutor for script generation ──
    if action_type == "video":
        try:
            from app.services.deeptutor_client import generate_video_script
            script = generate_video_script(f"{section_title}: {question[:200]}")
            if script and len(script) > 50:
                return {"status": "success", "data": {"reply": script, "content_type": "video_script"}}
        except Exception:
            pass

    is_targeted = bool(selected_excerpt)

    # ── Diagram: Mermaid for precision. AI image as bonus for conceptual topics.
    diagram_hint = ""
    if action_type == "diagram":
        diagram_hint = "\n请用 ```mermaid 绘制图解。铁律：第一行 flowchart LR（禁止 TD/TB），从左到右布局，节点ID英文，标签[中文]。"
    img_bonus = ""
    if action_type == "diagram" and is_targeted:
        _tech_kw = ["指令", "寄存器", "电路", "门", "总线", "时序", "流水线", "编码", "算法", "语法"]
        if not any(kw in selected_excerpt for kw in _tech_kw):
            try:
                from app.services.multimodal_registry import default_registry
                registry = default_registry()
                for task in ("image_generation", "image_generation_qwen"):
                    _, tool = registry.select_tool(task)
                    if tool:
                        r = tool.run({"user_message": f"教育配图:{selected_excerpt[:120]}", "session_id": session_id})
                        if r.get("status") == "success":
                            b64 = (r.get("result") or {}).get("image_base64") or r.get("image_base64", "")
                            if b64 and len(b64) > 200:
                                import base64 as _b64, os as _os, uuid as _uuid, time as _time
                                d = _os.path.join(_os.path.dirname(__file__), "..", "..", "data", "static", "images")
                                _os.makedirs(d, exist_ok=True)
                                fn = f"tutor_{_time.strftime('%H%M%S')}_{_uuid.uuid4().hex[:6]}.png"
                                with open(_os.path.join(d, fn), "wb") as f:
                                    f.write(_b64.b64decode(b64))
                                img_bonus = f"\n\n![配图](/static/images/{fn})"
                        break
            except Exception:
                pass

    # ── Build focused prompt when student selected specific content ──
    if is_targeted:
        prompt = f"""{tutor_persona}

学生选中了讲义中的一段内容，请针对这段内容进行解答：

【学生选中的内容】
{selected_excerpt}

【学生的问题】
{question}

要求：只针对选中的这段内容回答，不要扩展到整个章节。用 Markdown 格式。{diagram_hint}"""
    else:
        prompt = f"""{tutor_persona}

{profile_text if profile_text else ""}

当前学习内容：
- 小节：{section_title}
- 目标：{section_goal}
- 知识点：{kp_names}
{chr(10) + '讲义片段：' + chr(10) + lecture_excerpt if lecture_excerpt else ""}

学生问题：{question}{diagram_hint}

请用 Markdown 格式回答。如需图解用 ```mermaid 绘制。重点用 > 标注。回答要有针对性——结合学生画像中的薄弱点和学习风格来引导。"""

    client = _llm_client()
    try:
        raw = client.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048)
    except Exception as e:
        logger.warning("Tutor generation failed for section %s: %s", section_id, e)
        raw = ""

    if _is_invalid_tutor_reply(raw):
        raw = _fallback_tutor_reply(
            action_type,
            section_title,
            section_goal,
            knowledge_points if isinstance(knowledge_points, list) else [],
            lecture_excerpt,
            question,
        )

    content_type = "video_script" if action_type == "video" else ("diagram" if action_type == "diagram" else "text")
    return {"status": "success", "data": {"reply": raw, "content_type": content_type}}


@router.post("/sections/{section_id}/tutor/video")
def tutor_video(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """生成小节讲解短视频（调用 MultimodalAgent）。"""
    session_id = _payload_session_id(payload)
    section_title = str(payload.get("sectionTitle", "")).strip()
    requirements = str(payload.get("requirements", "")).strip()

    if not section_title:
        return _product_response(None, session_id=session_id, status="error", message="sectionTitle required", source="agent")

    user_msg = f"为小节「{section_title}」生成微课讲解视频"
    if requirements:
        user_msg += f"。学生特殊要求：{requirements}"

    try:
        from app.services.spark_provider import SparkVideoProvider
        provider = SparkVideoProvider()
        result = provider.run({
            "user_message": user_msg,
            "subject_name": section_title,
        })
        return _product_response({"video": _public_tutor_video(result)}, session_id=session_id, source="agent")
    except Exception as e:
        logger.warning("Tutor video failed for section %s: %s", section_id, e)
        return _product_response(None, session_id=session_id, status="error", message=f"视频生成失败: {e}", source="agent")


@router.post("/sections/{section_id}/resources/recommendations")
def recommend_section_resources(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return real external links for a section without archiving them as resources."""
    session_id = _payload_session_id(payload)
    section_title = str(payload.get("sectionTitle") or "").strip()
    knowledge_points = payload.get("knowledgePoints") or []
    if not section_title:
        try:
            from app.services.agent_service import get_learning_path
            for stage in (get_learning_path(session_id) or {}).get("stages", []):
                for chapter in stage.get("chapters", []):
                    for section in chapter.get("sections", []):
                        if str(section.get("section_id") or section.get("id") or "") == section_id:
                            section_title = str(section.get("title") or "").strip()
                            knowledge_points = section.get("knowledge_points") or section.get("knowledgePoints") or []
                            break
        except Exception:
            pass
    if not section_title:
        return _product_response(None, session_id=session_id, status="error", message="sectionTitle required", source="agent")

    profile: dict[str, Any] | None = None
    weak_points: list[Any] = []
    try:
        from app.services.agent_service import get_analytics, get_profile
        profile = get_profile(session_id)
        analytics = get_analytics(session_id) or {}
        weak_points = analytics.get("weakTopics") or []
    except Exception:
        pass

    from app.services.section_resource_recommendations import SectionResourceRecommendationService
    result = SectionResourceRecommendationService().recommend(
        session_id=session_id,
        section_id=section_id,
        section_title=section_title,
        knowledge_points=knowledge_points if isinstance(knowledge_points, list) else [],
        language=str(payload.get("language") or "zh-CN"),
        resource_types=payload.get("resourceTypes") if isinstance(payload.get("resourceTypes"), list) else [],
        profile=profile,
        weak_points=weak_points,
    )
    return _product_response({"recommendations": result}, session_id=session_id, source="duckduckgo")


def _section_path_context(session_id: str, section_id: str) -> dict[str, Any]:
    """Read existing path metadata; no planner call or path mutation."""
    try:
        path = ag_get_learning_path(session_id) or {}
        for stage in path.get("stages", []):
            for chapter in stage.get("chapters", []):
                for section in chapter.get("sections", []):
                    if str(section.get("section_id") or section.get("id") or "") == section_id:
                        return {
                            "path_id": path.get("id", ""), "stage_id": stage.get("stage_id") or stage.get("id", ""),
                            "chapter_id": chapter.get("chapter_id") or chapter.get("id", ""), "section_title": section.get("title", ""),
                            "knowledge_points": section.get("knowledge_points") or section.get("knowledgePoints") or [],
                        }
    except Exception:
        pass
    return {}


@router.post("/sections/{section_id}/resources/generate")
def generate_section_resource(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Generate one small section resource and archive it in the existing library."""
    session_id = _payload_session_id(payload)
    resource_type = str(payload.get("resourceType") or "").strip()
    context = _section_path_context(session_id, section_id)
    section_title = str(payload.get("sectionTitle") or context.get("section_title") or "").strip()
    if not section_title:
        return _product_response(None, session_id=session_id, status="error", message="sectionTitle required", source="agent")
    from app.services.section_generated_resources import SectionGeneratedResourcesService
    service = SectionGeneratedResourcesService()
    try:
        db = SessionLocal()
        existing = service.existing(db, session_id, section_id, resource_type)
        if existing is not None and not bool(payload.get("regenerate")):
            return _product_response({"resource": service.serialize(existing), "reused": True}, session_id=session_id, source="db")
        lecture = db.query(ResourceModel).filter(
            ResourceModel.session_id == session_id,
            ResourceModel.related_section_id == section_id,
            ResourceModel.type == "lecture",
        ).order_by(ResourceModel.updated_at.desc()).first()
        resource = service.generate(
            session_id=session_id, path_id=str(payload.get("pathId") or context.get("path_id") or ""),
            stage_id=str(payload.get("stageId") or context.get("stage_id") or ""),
            chapter_id=str(payload.get("chapterId") or context.get("chapter_id") or ""),
            section_id=section_id, section_title=section_title,
            lecture_content=str(payload.get("lectureContent") or (lecture.content if lecture else "") or ""),
            knowledge_points=payload.get("knowledgePoints") if isinstance(payload.get("knowledgePoints"), list) else context.get("knowledge_points", []),
            resource_type=resource_type,
            profile=_profile_v2(session_id),
        )
        saved = service.persist(db, session_id, resource)
        return _product_response({"resource": service.serialize(saved), "reused": False}, session_id=session_id, source="agent")
    except ValueError:
        return _product_response(None, session_id=session_id, status="error", message="unsupported resourceType", source="agent")
    finally:
        db.close()


@router.get("/sections/{section_id}/generated-resources")
def get_generated_section_resources(section_id: str, sessionId: str = "") -> dict[str, Any]:
    """Read only resources generated for the current section."""
    session_id = _require_session_id(sessionId)
    from app.services.section_generated_resources import SectionGeneratedResourcesService
    try:
        db = SessionLocal()
        rows = db.query(ResourceModel).filter(
            ResourceModel.session_id == session_id,
            ResourceModel.related_section_id == section_id,
        ).order_by(ResourceModel.updated_at.desc()).all()
        resources = [SectionGeneratedResourcesService.serialize(row) for row in rows if "section_generated" in (row.tags or [])]
        return _product_response({"resources": resources}, session_id=session_id, source="db")
    finally:
        db.close()


def _chapter_path_context(session_id: str, chapter_id: str) -> dict[str, Any]:
    try:
        path = ag_get_learning_path(session_id) or {}
        for stage in path.get("stages", []):
            for chapter in stage.get("chapters", []):
                if str(chapter.get("chapter_id") or chapter.get("id") or "") == chapter_id:
                    return {
                        "path_id": path.get("id", ""), "stage_id": stage.get("stage_id") or stage.get("id", ""),
                        "chapter_title": chapter.get("title", ""), "sections": chapter.get("sections", []),
                    }
    except Exception:
        pass
    return {}


@router.post("/chapters/{chapter_id}/mindmap/generate")
def generate_chapter_mindmap(chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Generate one local Mermaid mind map for a chapter and archive it."""
    session_id = _payload_session_id(payload)
    context = _chapter_path_context(session_id, chapter_id)
    chapter_title = str(payload.get("chapterTitle") or context.get("chapter_title") or "").strip()
    if not chapter_title:
        return _product_response(None, session_id=session_id, status="error", message="chapterTitle required", source="agent")
    from app.services.chapter_mindmap_resources import ChapterMindmapResourceService
    service = ChapterMindmapResourceService()
    try:
        db = SessionLocal()
        resource = service.generate(
            path_id=str(payload.get("pathId") or context.get("path_id") or ""),
            stage_id=str(payload.get("stageId") or context.get("stage_id") or ""),
            chapter_id=chapter_id, chapter_title=chapter_title,
            sections=payload.get("sections") if isinstance(payload.get("sections"), list) else context.get("sections", []),
        )
        saved = service.persist(db, session_id, resource)
        return _product_response({"mindmap": service.serialize(saved), "reused": False}, session_id=session_id, source="agent")
    except ValueError:
        return _product_response(None, session_id=session_id, status="error", message="思维导图生成失败，请稍后重试", source="agent")
    finally:
        db.close()


@router.get("/chapters/{chapter_id}/mindmap")
def get_chapter_mindmap(chapter_id: str, sessionId: str = "") -> dict[str, Any]:
    session_id = _require_session_id(sessionId)
    from app.services.chapter_mindmap_resources import ChapterMindmapResourceService
    try:
        db = SessionLocal()
        resource = ChapterMindmapResourceService().existing(db, session_id, chapter_id)
        return _product_response({"mindmap": ChapterMindmapResourceService.serialize(resource) if resource else None}, session_id=session_id, source="db")
    finally:
        db.close()


# ── Section-level mindmap ──

@router.post("/sections/{section_id}/mindmap/generate")
def generate_section_mindmap(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a mindmap scoped to a single section's knowledge points."""
    session_id = _payload_session_id(payload)
    section_title = str(payload.get("sectionTitle") or "").strip()
    knowledge_points = payload.get("knowledgePoints") if isinstance(payload.get("knowledgePoints"), list) else []
    if not section_title:
        return _product_response(None, session_id=session_id, status="error", message="sectionTitle required", source="agent")
    from app.services.chapter_mindmap_resources import ChapterMindmapResourceService
    service = ChapterMindmapResourceService()
    try:
        db = SessionLocal()
        resource = service.generate(
            path_id=str(payload.get("pathId") or ""),
            stage_id=str(payload.get("stageId") or ""),
            chapter_id=section_id,
            chapter_title=section_title,
            sections=[{"title": section_title, "knowledgePoints": knowledge_points}],
        )
        resource["id"] = f"section_{section_id}_mindmap"
        resource["title"] = f"{section_title} · 小节思维导图"
        saved = service.persist(db, session_id, resource)
        return _product_response({"mindmap": service.serialize(saved), "reused": False}, session_id=session_id, source="agent")
    except ValueError:
        return _product_response(None, session_id=session_id, status="error", message="思维导图生成失败", source="agent")
    finally:
        db.close()


@router.get("/sections/{section_id}/mindmap")
def get_section_mindmap(section_id: str, sessionId: str = "") -> dict[str, Any]:
    session_id = _require_session_id(sessionId)
    from app.services.chapter_mindmap_resources import ChapterMindmapResourceService
    try:
        db = SessionLocal()
        resource = ChapterMindmapResourceService().existing(db, session_id, f"section_{section_id}_mindmap")
        return _product_response({"mindmap": ChapterMindmapResourceService.serialize(resource) if resource else None}, session_id=session_id, source="db")
    finally:
        db.close()


# 画像推荐
@router.get("/profile/recommendations")
def get_profile_recommendations(sessionId: str = "") -> dict[str, Any]:
    session_id = _require_session_id(sessionId)
    try:
        db = SessionLocal()
        from app.services.agent_service import get_profile as ag_profile
        from app.db.repository import get_resources as repo_resources, get_latest_learning_path, get_event_analytics
        profile = ag_profile(session_id)
        resources = repo_resources(db, session_id)
        path = get_latest_learning_path(db, session_id)
        analytics = get_event_analytics(db, session_id)
        weak_topics = analytics.get("weakTopics", []) if analytics else []
        from app.services.recommendation_engine import generate_recommendations
        recs = generate_recommendations(
            session_id=session_id, weak_topics=weak_topics,
            resources=resources, learning_path=path, profile=profile, db=db,
        )
        return _product_response({"recommendations": recs}, session_id=session_id, source="db")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Notification endpoints — closed-loop assessment notifications
# ═══════════════════════════════════════════════════════════════════════


@router.get("/notifications")
def get_notifications(sessionId: str = "") -> dict[str, Any]:
    """Return pending assessment-loop notifications for a session.

    Notifications are consumed (removed) on read — the frontend should
    display them and then the next poll returns an empty list.
    """
    session_id = _require_session_id(sessionId)
    try:
        from app.services.assessment_loop import notification_store

        items = notification_store.pop_all(session_id)
        return _product_response(
            {"notifications": items, "hasMore": False},
            session_id=session_id,
            source="assessment_loop",
        )
    except Exception:
        return _product_response(
            {"notifications": [], "hasMore": False},
            session_id=session_id,
            source="assessment_loop",
        )


@router.get("/notifications/pending")
def has_pending_notifications(sessionId: str = "") -> dict[str, Any]:
    """Check whether there are pending notifications without consuming them."""
    session_id = _require_session_id(sessionId)
    try:
        from app.services.assessment_loop import notification_store

        has = notification_store.has_pending(session_id)
        return _product_response(
            {"hasPending": has},
            session_id=session_id,
            source="assessment_loop",
        )
    except Exception:
        return _product_response(
            {"hasPending": False},
            session_id=session_id,
            source="assessment_loop",
        )


@router.post("/notifications/ack")
def ack_notifications(payload: dict[str, Any]) -> dict[str, Any]:
    """Acknowledge/clear all notifications for a session."""
    session_id = str(payload.get("sessionId", "")).strip()
    if not session_id:
        return _product_response(None, status="error", message="sessionId required", source="assessment_loop")
    try:
        from app.services.assessment_loop import notification_store

        notification_store.pop_all(session_id)  # consume and discard
        return _product_response({"acknowledged": True}, session_id=session_id, source="assessment_loop")
    except Exception:
        return _product_response({"acknowledged": False}, session_id=session_id, source="assessment_loop")

