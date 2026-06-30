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

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.diagnosis_agent import DiagnosisAgent
from app.agents.conversation_agent import ConversationAgent
from app.config import settings
from app.db.engine import SessionLocal
from app.db.models import DailyTaskModel, LearnerModel, SessionModel
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
from app.utils.errors import InvalidEventTypeError, MissingSessionIdError, NotFoundError
from app.utils.profile_normalizer import PROFILE_DIMENSION_LABELS, normalize_profile_dimensions
from app.services.conversation_state import conversation_store
from app.services.course_catalog import course_catalog
from app.services.learning_tracker import learning_tracker
from app.services.llm_client import get_llm_client
from app.schemas.product import ProductApiResponse

router = APIRouter(tags=["product"])


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _profile_item(
    key: str,
    value: str,
    source: str = "user_input",
    confidence: float = 1.0,
    explanation: str | None = None,
    evidence: str | None = None,
    score: int = 70,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": PROFILE_DIMENSION_LABELS.get(key, key),
        "value": value,
        "score": score,
        "confidence": confidence,
        "source": source,
        "explanation": explanation or value,
        "evidence": evidence or value,
    }


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


def _apply_state_facts_to_result(result: dict[str, Any], state, course: dict[str, Any] | None = None) -> None:
    profile = result.setdefault("profile", {})
    course_name = str((course or {}).get("course_name") or state.facts.get("target_course") or "").strip()
    overrides = {
        "major_background": state.facts.get("background", ""),
        "knowledge_base": state.facts.get("knowledge_base", ""),
        "learning_goal": state.facts.get("learning_goal", ""),
        "cognitive_style": state.facts.get("preference", ""),
        "error_patterns": state.facts.get("weak_points", ""),
        "interest_direction": state.facts.get("target_course", ""),
        "learning_rhythm": state.facts.get("time_budget", ""),
    }
    for key, value in overrides.items():
        if value:
            profile[key] = _profile_item(
                key,
                str(value),
                source="user_input",
                confidence=1.0,
                explanation=f"该维度直接来自用户描述：{value}",
                evidence=str(value),
            )

    if course_name:
        profile["interest_direction"] = _profile_item(
            "interest_direction",
            course_name,
            source="user_input",
            confidence=0.9,
            explanation=f"目标课程已识别为：{course_name}",
            evidence=course_name,
            score=82,
        )
        profile.setdefault(
            "learning_progress",
            _profile_item(
                "learning_progress",
                f"正在推进{course_name}学习",
                source="inferred",
                confidence=0.8,
                explanation="根据目标课程和当前对话推断学习进度仍处于推进阶段。",
                evidence=course_name,
                score=60,
            ),
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
    }


def _classify_intent(message: str, session_id: str | None = None) -> dict[str, Any]:
    """用 ConversationAgent 进行对话理解，返回包含 reply 和 action 的结果。"""
    agent = ConversationAgent(mock_data={}, llm_client=_llm_client())
    context = _intent_context(session_id)
    context["user_message"] = message
    if "profile_facts" not in context:
        context["profile_facts"] = {}
    context["profile_facts"]["_raw_user_message"] = message

    # 加载对话历史
    if session_id:
        state = conversation_store.get(session_id)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in state.messages[-20:]
        ]
        context["conversation_history"] = history

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
    _apply_state_facts_to_result(result, state, selected_course)
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
        "mermaidDef": content if content_fmt == "mermaid" else None,
        "codeBlocks": item.get("code_blocks"),
        "questions": item.get("items"),
        "pptOutline": item.get("ppt_outline"),
        "createdAt": int(time.time() * 1000),
        "bookmarked": resource_id in bookmarks,
        "studyStatus": item.get("studyStatus", "new"),
        "completedAt": item.get("completedAt") or item.get("completed_at"),
        "source": _source_label(item.get("source", "")),
        "relatedStageId": related_stage_id,
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
    """Convert raw orchestrator-format stages (with tasks) to frontend-format stages (with nodes).

    Raw format: [{"stage_id": "s1", "title": "...", "tasks": ["task1"], "resource_types": ["lecture"], ...}, ...]
    Frontend:   [{"id": "s1", "order": 1, "title": "...", "nodes": [{...}, ...], ...}, ...]
    """
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
    if not session_id:
        raise ValueError("session_id is required for _casual_reply")
    state = conversation_store.get(session_id)
    known = "\n".join(conversation_store.known_lines(state))
    if known:
        return (
            "你好，我是 EduAgent。"
            "你刚才提供的信息我已经记录了，"
            "不用重新填表。\n\n"
            "我目前已记录：\n"
            f"{known}\n\n"
            "你可以继续补充想学的课程、"
            "已有基础、目标或偏好；"
            "也可以直接说「开始生成学习方案」。"
        )
    return (
        "你好，我是 EduAgent。你可以告诉我你的专业、学习基础、目标和偏好的学习方式，"
        "我会帮你生成学习画像、学习路径和个性化资源。\n\n"
        "例如：我是软件工程大三学生，Python 和数据结构还可以，但线性代数比较弱，"
        "想用十天学懂神经网络，希望多给我代码实验和图解。"
    )


def _date_query_reply() -> str:
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"今天是 {now.year} 年 {now.month} 月 {now.day} 日，{weekdays[now.weekday()]}。"


def _clarification_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    if not state.messages:
        return "我刚刚没有足够上下文可以解释。你可以把不理解的那句话再发我一次。"

    known = "\n".join(conversation_store.known_lines(state)) or "- 暂时还没有稳定学习画像"
    questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=2))
    return (
        "我的意思是：我会先通过对话收集你的学习画像，再根据画像生成学习路径和资源。\n\n"
        f"当前我已记录：\n{known}\n\n"
        f"如果你想继续生成个性化学习方案，下一步最有用的是补充：\n{questions}"
    )


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
    if not known:
        known = "- 暂时还没有稳定画像信息"

    if not missing:
        return (
            "你目前提供的信息已经够我生成第一版学习画像和学习路径了。\n\n"
            f"我已记录的信息：\n{known}\n\n"
            "下一步你可以直接说「开始生成学习方案」，或者继续补充最近做题情况、错题类型和喜欢的资源形式，我会继续更新画像。"
        )

    questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=2))
    return (
        "可以，我会根据你已经说过的信息继续补全画像，不需要一次性填表。\n\n"
        f"{_readiness_line(session_id)}\n\n我目前已记录：\n{known}\n\n"
        f"接下来最有用的是补充这几项：\n{questions}\n\n"
        "你可以直接用一句话回答，例如：我数据结构基础一般，链表和树比较薄弱，想两周内能做课程实验，更喜欢图解加代码。"
    )


def _profile_query_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    if state.last_result is None:
        known, missing = _format_known_and_missing(session_id)
        if known:
            questions = "\n".join(f"- {item['question']}" for item in missing[:3])
            return (
                "我现在已经能形成一个很粗的学习画像，但还不够完整。\n\n"
                f"已记录的信息：\n{known}\n\n"
                f"建议你继续补充：\n{questions}"
            )
        return (
            "我现在还没有足够信息判断你是什么类型的学习者。\n\n"
            "你可以告诉我你的专业、年级、学过什么、哪里薄弱、想达成什么目标。"
            "我会先构建学习画像，再基于画像回答你适合的学习方向和学习策略。"
        )

    profile = _to_profile(state.last_result)
    descriptions = [
        f"{dimension['label']}：{dimension['description']}"
        for dimension in profile["dimensions"]
        if dimension.get("description")
    ]
    summary = "\n".join(f"- {item}" for item in descriptions[:6])
    known, missing = _format_known_and_missing(session_id)
    missing_text = "\n".join(f"- {item['label']}" for item in missing[:3]) or "- 暂无明显缺失"
    return (
        "根据目前已有的学习画像，我对你的判断是：\n\n"
        f"{summary}\n\n"
        f"会话中额外记录的信息：\n{known or '- 暂无'}\n\n"
        f"后续还可以补充：\n{missing_text}\n\n"
        "这不是性格判断，而是基于你提供的学习背景、目标和偏好形成的学习画像。"
        "如果你补充更多学习经历或练习反馈，我可以继续更新这个判断。"
    )


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
        return (
            "收到，我已经把这条信息更新进你的学习画像了。\n\n"
            f"本次更新：\n{update_text}{conflict_notice}\n\n"
            f"{_readiness_line(session_id)}，已经可以生成第一版学习方案。\n\n"
            f"当前画像信息：\n{known}\n\n"
            "你可以继续补充薄弱点、学习时间或资源偏好；也可以直接说「开始生成学习方案」，我会启动多智能体生成学习路径和资源。"
        )

    if not updated and supplemental_updated:
        return (
            "收到，这条信息我会作为补充背景保留，但它还不足以决定学习路径。\n\n"
            f"本次记录：\n{supplemental_updated}{conflict_notice}\n\n"
            f"{_readiness_line(session_id)}\n\n"
            f"为了真正生成个性化学习方案，接下来更需要补充：\n{missing_questions}"
        )

    return (
        "收到，我已经把这条信息记进你的学习画像了。\n\n"
        f"本次更新：\n{update_text}{conflict_notice}\n\n"
        f"{_readiness_line(session_id)}\n\n当前已记录：\n{known or '- 暂时还没有稳定画像信息'}\n\n"
        f"为了更准确地规划，接下来建议你补充：\n{missing_questions}"
    )


def _start_advice_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, _ = _format_known_and_missing(session_id)

    if not known and state.last_result is None:
        return (
            "如果你是第一次使用，我还不能直接判断你该从哪一步开始，因为我还没有你的学习画像。\n\n"
            "你先用一句话告诉我三个信息就够了：你是谁、想学什么、现在基础怎么样。\n"
            "例如：我是软件工程大三学生，Python 和数据结构还可以，线性代数比较弱，想用十天学懂神经网络。"
        )

    if state.last_result:
        path = state.last_result.get("learning_path", [])
        first_stage = path[0] if path else {}
        first_task = (first_stage.get("tasks") or ["先阅读入门讲义"])[0]
        stage_title = first_stage.get("title", "第一阶段")
        return (
            "我建议你从学习路径的第一步开始，而不是直接跳到练习或项目。\n\n"
            f"当前建议起点：{stage_title}\n"
            f"第一件事：{first_task}\n\n"
            "原因是这一步通常负责补齐概念框架，后面的题库、代码实验和拓展阅读才更容易吸收。"
            "你可以先去「学习路径」页面看第 1 阶段，再到「资源库」打开对应讲义。"
        )

    target = state.facts.get("target_course", "目标课程")
    weak = state.facts.get("weak_points") or state.facts.get("knowledge_base") or "当前薄弱基础"
    return (
        f"按你目前提供的信息，我建议先从「{target}」的基础概念层开始。\n\n"
        f"我已记录的信息：\n{known}\n\n"
        f"原因：你现在最需要先把「{weak}」对应的前置概念理顺，再进入练习和项目。\n"
        "如果你希望我给出完整路径，可以直接说「开始生成学习方案」。"
    )


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
    return (
        "我理解你是在寻求知识点讲解或问题辅导。\n\n"
        f"你的问题是：{message}\n\n"
        "当前第一阶段还没有完整接入 TutorAgent，我可以先建议你补充："
        "课程名称、具体知识点、题目或代码片段。后续会由 KnowledgeAgent + TutorAgent "
        "给出文字解释、图解说明和练习建议。"
    )


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
        }
        for llm_key, fact_key in fact_mapping.items():
            value = str(llm_facts.get(llm_key, "")).strip()
            if value and len(value) >= 2:
                invalid = {"的是什么", "的是什么诶", "什么", "啥", "这个", "那个", "它", "他", "她", "未知", "未提及", "无", "none"}
                if value not in invalid:
                    state.facts[fact_key] = value

    llm_reply = intent.get("reply", "")
    action = intent.get("action", "none")

    # ── 无上下文确认词追问 ──
    if intent.get("needs_clarification") and action == "none" and _is_bare_confirmation(message):
        return _confirmation_clarification_reply(), False

    # ── action=none：纯对话，不执行 Agent ──
    if action == "none":
        return llm_reply or _casual_reply(session_id), False

    # ── 安全检查 ──
    if action == "unsafe":
        return llm_reply or "抱歉，我不能协助这类请求。如果你有学习相关的问题，我很乐意帮忙。", False

    # ── action 需要执行 Agent ──
    agent_actions = ("full_workflow", "diagnose", "plan", "resources", "profile", "knowledge")
    if action in agent_actions:
        # 硬条件检查：如果连学习对象都不知道，必须先问（§2.3）
        if action in ("full_workflow", "plan"):
            state = conversation_store.get(session_id)
            if not _learning_subject(state):
                return _ask_learning_subject_reply(), False

        # §4.1 + §11.1：根据 action 只调需要的子 Agent，不全量跑
        agents_filter = _agents_for_action(action)
        logger.info("Scheduling agents for action=%s: %s", action, agents_filter)

        try:
            result = _run_agents(message, session_id=session_id,
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
        return final_reply, bool(result.get("learning_path"))

    # 兜底
    return llm_reply or _casual_reply(session_id), False


def _agents_for_action(action: str) -> list[str] | None:
    """根据 ConversationAgent 的 action 返回需要运行的 Agent 列表（§4.1, §11.1）。
    返回 None 表示全量运行。
    """
    if action == "full_workflow":
        return None  # 全量
    if action == "diagnose":
        return ["profile_agent", "diagnosis_agent"]
    if action == "plan":
        return ["profile_agent", "knowledge_agent", "diagnosis_agent", "planner_agent"]
    if action == "resources":
        return ["profile_agent", "planner_agent", "resource_agent"]
    if action == "profile":
        return ["profile_agent"]
    if action == "knowledge":
        return ["profile_agent", "knowledge_agent"]
    return None


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
            "resources_created": bool(resources),
            "resource_count": len(resources),
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
        return "生成流程已完成。你可以到学习路径和资源库页面查看详细内容。"
    return "、".join(parts) + "。你可以到对应页面查看详细内容。"


def _will_run_agents(intent: dict[str, Any], session_id: str) -> bool:
    """Check whether the given intent will trigger agent execution."""
    action = intent.get("action", "")
    return action in ("diagnose", "plan", "resources", "full_workflow", "knowledge", "profile")


GEN_STAGES = [
    ("understanding", "正在理解需求", 5),
    ("profiling",    "正在生成画像", 25),
    ("planning",     "正在规划路径", 50),
    ("generating",   "正在生成资源", 75),
    ("saving",       "正在保存结果", 95),
]


@router.post("/chat/stream")
def stream_chat(payload: dict[str, Any]) -> StreamingResponse:
    message = str(payload.get("message", "我想学习人工智能导论"))
    session_id = _payload_session_id(payload)
    subject_id = _payload_subject_id(payload)
    _validate_message(message)

    # Link session to subject/learner for proper data isolation
    _ensure_session_linked(session_id, subject_id=subject_id)

    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message, session_id)
    conversation_store.set_intent(session_id, intent)
    run_agents = _will_run_agents(intent, session_id)

    def _to_event(stage: str, agent: str, pct: int, **kw) -> str:
        data = {"stage": stage, "agentName": agent, "progress": pct, "done": False, **kw}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def event_stream():
        nonlocal run_agents
        if run_agents:
            # ── 先发「正在理解需求」，让用户立刻感知响应 ──
            s0_label, s0_key, s0_pct = "正在理解需求", "understanding", 5
            yield _to_event(s0_label, s0_key, s0_pct)

            # Mark generation as in-progress for recovery
            state = conversation_store.get(session_id)
            state.generating = True

            # ── 在线程中执行智能体，通过队列实时回传进度 ──
            progress_q: Queue = Queue()
            result_box: dict[str, Any] = {}

            def _agent_worker():
                try:
                    # 后端细粒度阶段 → 前端 5 阶段映射
                    _STAGE_MAP = {
                        "profiling":   ("profiling", "正在生成画像"),
                        "knowledge":   ("profiling", "正在生成画像"),
                        "diagnosis":   ("profiling", "正在生成画像"),
                        "planning":    ("planning", "正在规划路径"),
                        "generating":  ("generating", "正在生成资源"),
                        "reviewing":   ("generating", "正在生成资源"),
                    }
                    def on_progress(
                        stage_key: str, stage_label: str, pct: int,
                        detail: str | None = None,
                    ):
                        mapped_key, mapped_label = _STAGE_MAP.get(
                            stage_key, (stage_key, stage_label)
                        )
                        progress_q.put(
                            ("progress", mapped_key, mapped_label, pct, detail)
                        )
                        # Persist live progress so recovery endpoint can replay it
                        st = conversation_store.get(session_id)
                        st.current_progress = {
                            "stage": mapped_label,
                            "agentName": mapped_key,
                            "progress": pct,
                            "detail": detail,
                        }
                    reply, ran = _reply_for_intent(
                        message, intent, session_id,
                        progress_callback=on_progress,
                    )
                    result_box["reply"] = reply
                    result_box["ran"] = ran
                    # Persist reply immediately in worker thread so it survives
                    # client disconnect (main generator may never reach line 1346).
                    conversation_store.append_message(session_id, "assistant", reply)
                    # Clear generation state for recovery endpoint
                    state = conversation_store.get(session_id)
                    state.generating = False
                    state.current_progress = None
                    progress_q.put(("done",))
                except Exception as exc:
                    result_box["error"] = exc
                    # Persist error so recovery endpoint can surface it
                    conversation_store.append_message(session_id, "assistant", f"[生成失败] {exc}")
                    # Clear generation state on error too
                    state = conversation_store.get(session_id)
                    state.generating = False
                    state.current_progress = None
                    progress_q.put(("error",))

            t = threading.Thread(target=_agent_worker, daemon=True)
            t.start()

            # ── 从队列读取实时进度事件 ──
            last_keepalive = time.monotonic()
            while t.is_alive() or not progress_q.empty():
                try:
                    msg = progress_q.get(timeout=0.5)
                    kind = msg[0]
                    if kind == "progress":
                        _, stage_key, stage_label, pct, detail = msg
                        extra: dict[str, Any] = {}
                        if detail:
                            extra["detail"] = detail
                        yield _to_event(stage_label, stage_key, pct, **extra)
                    elif kind == "done":
                        break
                    elif kind == "error":
                        err = result_box.get("error", Exception("未知错误"))
                        yield _to_event("生成失败", "failed", 0, error=str(err), done=True)
                        yield 'data: {"done":true}\n\n'
                        return
                except Empty:
                    # ponytail: low-rate keepalive prevents long resource generation from looking stuck at 80%.
                    if time.monotonic() - last_keepalive >= 10:
                        st = conversation_store.get(session_id)
                        progress = st.current_progress or {
                            "stage": "正在生成资源",
                            "agentName": "generating",
                            "progress": 80,
                        }
                        yield _to_event(
                            progress.get("stage", "正在生成资源"),
                            progress.get("agentName", "generating"),
                            int(progress.get("progress", 80) or 80),
                            keepalive=True,
                            detail=progress.get("detail"),
                        )
                        last_keepalive = time.monotonic()
                    # 仍在等待中 — 可发心跳保持连接活跃
                    continue

            # ── 处理结果 ──
            if "error" in result_box:
                yield _to_event("生成失败", "failed", 0, error=str(result_box["error"]), done=True)
                yield 'data: {"done":true}\n\n'
                return

            reply = result_box.get("reply", "")
            ran = result_box.get("ran", False)
            if not ran:
                run_agents = False

            # ── 推进到「保存结果」(reply already saved in worker thread) ──
            yield _to_event("正在保存结果", "saving", 95)
            yield _to_event("正在保存结果", "saving", 100)

            # ── 流式输出回复内容 ──
            for chunk in reply.splitlines(keepends=True):
                yield f"data: {json.dumps({'content': chunk, 'done': False}, ensure_ascii=False)}\n\n"
        else:
            # ── action=none，直接返回 LLM 回复，不执行 Agent ──
            llm_reply = intent.get("reply", "")
            if llm_reply:
                reply = llm_reply
                ran_agents = False
            else:
                reply, ran_agents = _reply_for_intent(message, intent, session_id)
            
            conversation_store.append_message(session_id, "assistant", reply)
            
            if ran_agents:
                # 触发了 Agent — 显示完成阶段
                for stage_key, stage_label, pct in GEN_STAGES:
                    yield f"data: {json.dumps({'stage': stage_label, 'agentName': stage_key, 'progress': pct, 'done': False}, ensure_ascii=False)}\n\n"
            
            for chunk in reply.splitlines(keepends=True):
                yield f"data: {json.dumps({'content': chunk, 'done': False}, ensure_ascii=False)}\n\n"

        result = conversation_store.get(session_id).last_result or {}
        stages = result.get("learning_path", []) if isinstance(result, dict) else []
        resources = result.get("resources", []) if isinstance(result, dict) else []
        final_event: dict[str, Any] = {
            "event": "done",
            "done": True,
            "sessionId": session_id,
            # ── 执行状态 ──
            "pipeline_executed": bool(result.get("pipeline_executed")) if isinstance(result, dict) else False,
            "agents_run": result.get("agents_run", []) if isinstance(result, dict) else [],
            "learning_path_created": bool(stages),
            "stage_count": len(stages),
            "resources_created": bool(resources),
            "resource_count": len(resources),
            "planner_metadata": result.get("planner_metadata", {}) if isinstance(result, dict) else {},
            # ── debug 字段（§12.1）──
            "action": intent.get("action", "none"),
            "confidence": intent.get("confidence", 0),
            "should_run_pipeline": not result.get("skip_pipeline", True),
            "skip_pipeline": result.get("skip_pipeline", False),
            "skip_reason": result.get("skip_reason", ""),
            "final_reply_owner": "conversation_agent",
            "reply_source": result.get("source", ""),
            "fallback_used": result.get("fallback_used", False),
            "llm_retry_count": intent.get("llm_retry_count", 0),
        }
        if intent.get("action") == "diagnose" or intent.get("intent") == "diagnosis":
            final_event["diagnosis"] = result.get("diagnosis", {})
        yield f"data: {json.dumps(final_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/send")
def send_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "我想学习人工智能导论"))
    session_id = _payload_session_id(payload)
    subject_id = _payload_subject_id(payload)
    _validate_message(message)

    # Link session to subject/learner for proper data isolation
    _ensure_session_linked(session_id, subject_id=subject_id)

    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message, session_id)
    conversation_store.set_intent(session_id, intent)
    reply, _ = _reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", reply)
    response = {
        "sessionId": session_id,
        "reply": {
            "id": "assistant_msg_001",
            "role": "assistant",
            "content": reply,
            "timestamp": int(time.time() * 1000),
        },
        "intent_result": _public_intent_result(intent),
    }
    result = conversation_store.get(session_id).last_result or {}
    diagnosis = result.get("diagnosis", {}) if isinstance(result, dict) else {}
    if intent.get("action") == "diagnose" or intent.get("intent") == "diagnosis" or (
        isinstance(diagnosis, dict) and diagnosis and _looks_like_diagnosis_reply(reply)
    ):
        response["diagnosis"] = diagnosis
    return _product_response(
        response,
        session_id=session_id, source="agent",
    )


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
def quick_commands() -> dict[str, Any]:
    """Return quick-command suggestions for the chat input.

    Commands are dynamically enriched with available course names from the
    catalog so the frontend always shows relevant prompts.
    """
    base_commands = [
        {"id": "ai_intro", "label": "AI 入门", "icon": "Brain", "prompt": "我是大二学生，想两周入门人工智能"},
        {"id": "nn", "label": "神经网络", "icon": "Brain", "prompt": "我想重点学习神经网络，希望多给图解和代码"},
        {"id": "data_structures", "label": "数据结构", "icon": "BookOpen", "prompt": "我是软件工程大二学生，想复习数据结构，为了考试通过"},
    ]

    # Enrich with available courses from the catalog
    try:
        for course in course_catalog.list_courses()[:2]:
            name = course.get("course_name", "")
            if name and not any(c["label"] == name for c in base_commands):
                base_commands.append({
                    "id": f"course_{course.get('course_id', '')}",
                    "label": name,
                    "icon": "BookOpen",
                    "prompt": f"我想学习{name}，请帮我生成个性化学习方案",
                })
    except Exception:
        logger.warning("Failed to enrich quick commands from course catalog")

    return _product_response(
        {"commands": base_commands},
        source="catalog",
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
    """
    if not subject_id and not learner_id:
        return
    try:
        db = SessionLocal()
        sess = db.get(SessionModel, session_id)
        if sess is None:
            from app.db.repository import get_or_create_learner
            learner = get_or_create_learner(db, learner_id)
            sess = SessionModel(
                id=session_id,
                learner_id=learner.id,
                subject_id=subject_id or None,
            )
            db.add(sess)
            db.commit()
        else:
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
        logger.warning("Failed to link session %s to subject/learner", session_id)
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
            }},
            session_id=session_id, subject_id=subjectId, source="db",
        )

    # Fall back to in-memory last_result if available (transitional)
    state = conversation_store.get(session_id)
    if state.last_result:
        profile = _to_profile(state.last_result)
        readiness = conversation_store.readiness(state)
        profile["source"] = "agent_generated"
        profile["readiness"] = readiness
        return _product_response({"profile": profile}, session_id=session_id, subject_id=subjectId, source="agent")

    # No data at all — return empty structure
    return _product_response({"profile": _empty_profile(session_id)}, session_id=session_id, subject_id=subjectId, source="none")


@router.post("/profile/build")
def build_profile(payload: dict[str, Any]) -> dict[str, Any]:
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

    return _product_response({"profile": profile}, session_id=session_id, source="agent")


@router.patch("/profile")
def update_profile(payload: dict[str, Any]) -> dict[str, Any]:
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
def generate_resource(payload: dict[str, Any]) -> dict[str, Any]:
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
def generate_learning_path(payload: dict[str, Any]) -> dict[str, Any]:
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
def auto_advance_node(payload: dict[str, Any]) -> dict[str, Any]:
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
    return _product_response(
        {
            **analytics,
            "summary": "已接入学习事件追踪，可用于后续动态调整画像、资源推荐和学习路径。",
        },
        session_id=session_id, subject_id=subjectId, source="db",
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
