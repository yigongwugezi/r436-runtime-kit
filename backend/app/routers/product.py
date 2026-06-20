"""Product-facing API routes for the EduAgent frontend.

Design principles (Stage 2):
- **Read endpoints** (GET) read directly from the database — they NEVER trigger agent runs.
- **Write/trigger endpoints** (POST) call ``agent_service.run_agents()``, persist results, and return them.
- All responses use the ``ApiResponse`` envelope for stable frontend contracts.
- Every endpoint requires ``sessionId`` — no hardcoded default.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.intent_agent import IntentAgent
from app.config import settings
from app.db.engine import SessionLocal
from app.db.models import LearnerModel, SessionModel
from app.db.repository import (
    get_bookmarked_ids,
    get_learner,
    get_learner_aggregated_profile,
    get_learner_sessions,
    get_messages as repo_get_messages,
    get_or_create_session,
    list_sessions as repo_list_sessions,
    save_profile_snapshot,
    toggle_bookmark,
)
from app.services.agent_service import (
    get_analytics as ag_get_analytics,
    get_learning_path as ag_get_learning_path,
    get_profile as ag_get_profile,
    get_resources as ag_get_resources,
    run_agents as ag_run_agents,
)
from app.utils.profile_normalizer import PROFILE_DIMENSION_LABELS, normalize_profile_dimensions
from app.services.conversation_state import conversation_store
from app.services.course_catalog import course_catalog
from app.services.learning_tracker import learning_tracker
from app.services.llm_client import get_llm_client

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


def _classify_intent(message: str) -> dict[str, Any]:
    return IntentAgent(mock_data={}, llm_client=_llm_client()).classify(message)


def _run_agents(
    message: str = "我想学习人工智能导论",
    session_id: str = "frontend_session_001",
) -> dict[str, Any]:
    """Trigger the full multi-agent pipeline via AgentService and persist results."""
    state = conversation_store.get(session_id)
    user_topic = state.facts.get("target_course") or message
    selected_course = course_catalog.match_course(user_topic)

    if selected_course is None:
        # No matching course in catalog — build a virtual course from the user's stated topic
        selected_course = {
            "course_id": f"custom_{abs(hash(user_topic)) % 10000:04d}",
            "course_name": user_topic.strip(),
            "description": f"用户自定义学习主题：{user_topic.strip()}",
            "chapters": [],
            "chapter_count": 0,
        }

    course_id = str(selected_course.get("course_id") or "ai_intro")
    result = ag_run_agents(
        session_id=session_id,
        user_message=message,
        course_id=course_id,
    )
    if selected_course and "course" not in result:
        result["course"] = {
            "course_id": selected_course.get("course_id"),
            "course_name": selected_course.get("course_name"),
            "description": selected_course.get("description", ""),
            "chapter_count": selected_course.get("chapter_count", len(selected_course.get("chapters", []))),
        }
    _apply_state_facts_to_result(result, state, selected_course)
    # Persistence is handled by agent_service.run_agents() — no duplicate set_result here.
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
        result.append({
            "key": key,
            "label": _DIMENSION_LABELS.get(key, dim.get("label", key)),
            "value": text_value,
            "score": score,
            "confidence": dim.get("confidence", 0.75),
            "description": explanation,
            "explanation": explanation,
            "evidence": str(dim.get("evidence", "")),
            "source": str(dim.get("source", "rule_based_fallback")),
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
    if key in {"learning_rhythm", "self_efficacy"}:
        return max(50, base)  # neutral default for new dimensions
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
    "self_efficacy": "学习效能",
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
            "suggestedResources": [],
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
            pass
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
    "rule_based_fallback": "fallback",
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
    return _SOURCE_MAP.get(source, source)


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
        "source": _source_label(item.get("source", "")),
        "relatedStageId": related_stage_id,
        "relatedChapter": related_chapter,
        "relatedKnowledgePoints": related_knowledge_points if isinstance(related_knowledge_points, list) else [related_knowledge_points],
        "qualityStatus": quality_status,
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
    course_id = result.get("course_id", "ai_intro")
    course_name = course.get("course_name") or ("人工智能导论" if course_id == "ai_intro" else str(course_id))
    raw_stages = result.get("learning_path", [])
    stages = _raw_stages_to_nodes(raw_stages)
    estimated_days = _estimated_path_days(raw_stages)

    return {
        "id": f"path_{course_id}",
        "title": f"{course_name}个性化学习路径",
        "description": result.get("diagnosis", {}).get("recommended_strategy", ""),
        "courseName": course_name,
        "stages": stages,
        "createdAt": int(time.time() * 1000),
        "overallProgress": result.get("overallProgress", 0),
        "estimatedDays": result.get("estimatedDays", estimated_days),
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
    profile = _to_profile(result)
    path = _to_learning_path(result)
    session_id = result.get("session_id", "")
    resources = [_to_resource(item, result.get("course_id", "ai_intro"), session_id) for item in result.get("resources", [])]
    weak = "、".join(item["topic"] for item in profile["weaknesses"][:3]) or "暂无明显短板"
    resource_names = "、".join(item["title"] for item in resources[:5])

    # Check if this is a custom (non-catalog) topic — no matching course in knowledge base
    course_id = result.get("course_id", "")
    knowledge_source = result.get("knowledge_context", {}).get("source", "")
    is_custom_course = course_id.startswith("custom_") or knowledge_source == "user_provided_topic"

    # Check if the learning path is empty (no stages) — no real data was generated
    if not path.get("stages") or len(path.get("stages", [])) == 0:
        return (
            "## 学习方案生成说明\n\n"
            "当前画像信息尚不足以生成完整的个性化学习路径。\n\n"
            f"- 意图识别：{intent['intent']}，置信度 {intent['confidence']:.0%}\n\n"
            "请补充你的专业背景、学习基础、薄弱点和学习目标等信息，"
            "我会重新生成针对性更强的学习路径。\n\n"
            "你可以直接告诉我：年级专业、已学过的课程、想学的方向、薄弱环节等。"
        )

    if is_custom_course:
        course_name = (result.get("course") or {}).get("course_name", "你的学习主题")
        return (
            f"## 学习方案已生成（通用框架）\n\n"
            f"⚠️ 当前知识库中没有「{course_name}」的课程资料，"
            "以下为基于你画像信息生成的通用学习路径框架。\n\n"
            f"- 意图识别：{intent['intent']}，置信度 {intent['confidence']:.0%}\n"
            f"- 已构建 {len(profile['dimensions'])} 维学生画像\n"
            f"- 识别的重点薄弱点：{weak}\n"
            f"- 学习路径：{path['estimatedDays']} 天，{len(path['stages'])} 个阶段\n\n"
            "你可以切换到「学习画像」「学习路径」和「资源库」页面查看结果。"
        )

    return (
        "## 个性化学习方案已生成\n\n"
        f"- 意图识别：{intent['intent']}，置信度 {intent['confidence']:.0%}\n"
        f"- 已构建 {len(profile['dimensions'])} 维学生画像\n"
        f"- 识别的重点薄弱点：{weak}\n"
        f"- 学习路径：{path['estimatedDays']} 天，{len(path['stages'])} 个阶段\n"
        f"- 已生成资源：{resource_names}\n\n"
        "你可以切换到「学习画像」「学习路径」和「资源库」页面查看完整结果。"
    )


def _casual_reply(session_id: str = "frontend_session_001") -> str:
    state = conversation_store.get(session_id)
    known = "\n".join(conversation_store.known_lines(state))
    if known:
        return (
            "\u4f60\u597d\uff0c\u6211\u662f EduAgent\u3002"
            "\u4f60\u521a\u624d\u63d0\u4f9b\u7684\u4fe1\u606f\u6211\u5df2\u7ecf\u8bb0\u5f55\u4e86\uff0c"
            "\u4e0d\u7528\u91cd\u65b0\u586b\u8868\u3002\n\n"
            "\u6211\u76ee\u524d\u5df2\u8bb0\u5f55\uff1a\n"
            f"{known}\n\n"
            "\u4f60\u53ef\u4ee5\u7ee7\u7eed\u8865\u5145\u60f3\u5b66\u7684\u8bfe\u7a0b\u3001"
            "\u5df2\u6709\u57fa\u7840\u3001\u76ee\u6807\u6216\u504f\u597d\uff1b"
            "\u4e5f\u53ef\u4ee5\u76f4\u63a5\u8bf4\u300c\u5f00\u59cb\u751f\u6210\u5b66\u4e60\u65b9\u6848\u300d\u3002"
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


def _learning_plan_request_reply(message: str, intent: dict[str, Any], session_id: str) -> tuple[str, bool]:
    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    force_generate_words = [
        "\u76f4\u63a5\u751f\u6210",
        "\u5148\u751f\u6210",
        "\u751f\u6210\u770b\u770b",
        "\u4e0d\u7528\u5728\u610f",
        "\u4e0d\u5728\u610f\u51c6\u4e0d\u51c6",
        "\u5148\u770b\u6548\u679c",
    ]
    force_generate = any(word in message for word in force_generate_words)
    if readiness["readyToPlan"] or force_generate:
        if force_generate and not readiness["readyToPlan"]:
            result = _run_agents(message, session_id=session_id)
            content = _learning_plan_reply(result, intent)
            return f"{content}\n\n低画像完整度生成：当前信息较少，本方案作为第一版草稿，后续可随画像更新继续调整。", True
        return _learning_plan_reply(_run_agents(message, session_id=session_id), intent), True

    questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=3))
    known = "\n".join(conversation_store.known_lines(state)) or "- 暂时还没有稳定画像信息"
    return (
        "我可以生成学习方案，但现在画像信息还不够，直接生成容易不准。\n\n"
        f"{_readiness_line(session_id)}\n\n"
        f"当前已记录：\n{known}\n\n"
        f"请先补充这几项中的至少一两项：\n{questions}\n\n"
        "补充后你再说「开始生成学习方案」，我会启动多智能体协同生成画像、路径和资源。",
        False,
    )


def _tutoring_reply(message: str) -> str:
    return (
        "我理解你是在寻求知识点讲解或问题辅导。\n\n"
        f"你的问题是：{message}\n\n"
        "当前第一阶段还没有完整接入 TutorAgent，我可以先建议你补充："
        "课程名称、具体知识点、题目或代码片段。后续会由 KnowledgeAgent + TutorAgent "
        "给出文字解释、图解说明和练习建议。"
    )


def _resource_request_reply(message: str, session_id: str) -> str:
    result = _run_agents(message, session_id=session_id)
    resources = [_to_resource(item, result.get("course_id", "ai_intro"), session_id) for item in result.get("resources", [])]
    names = "、".join(item["title"] for item in resources[:5])
    return (
        "我识别到你在请求学习资源。\n\n"
        f"当前已为你准备这些资源：{names}\n\n"
        "可以到「资源库」页面查看。后续 ResourceAgent 会进一步接入大模型，按主题实时生成讲义、题库、思维导图和实操案例。"
    )


def _feedback_reply(message: str, session_id: str) -> str:
    learning_tracker.log({"event": "chat_feedback", "metadata": {"message": message}}, session_id=session_id)
    return (
        "收到你的学习反馈了。我已经记录这次反馈，后续会用于调整画像、资源推荐和学习路径。\n\n"
        "学习事件已持久化保存。"
    )


def _unknown_reply(intent: dict[str, Any]) -> str:
    return (
        "我还不确定你这句话想让我做什么。\n\n"
        f"当前判断：{intent['intent']}，置信度 {intent['confidence']:.0%}。\n\n"
        "你可以说明你是想：规划学习路径、解释知识点、生成学习资源，还是反馈学习进度。"
    )


def _reply_for_intent(message: str, intent: dict[str, Any], session_id: str) -> tuple[str, bool]:
    name = intent["intent"]
    if name == "casual_chat":
        return _casual_reply(session_id), False
    if name == "date_query":
        return _date_query_reply(), False
    if name == "clarification":
        return _clarification_reply(session_id), False
    if name == "info_request":
        return _info_request_reply(session_id), False
    if name == "profile_query":
        return _profile_query_reply(session_id), False
    if name == "profile_update":
        # Auto-trigger agent pipeline if profile is ready — run BEFORE generating reply
        ran_agents = False
        state = conversation_store.get(session_id)
        if conversation_store.readiness(state)["readyToPlan"]:
            try:
                _run_agents(message, session_id=session_id)
                ran_agents = True
            except Exception:
                pass  # Don't block chat reply if agent run fails
        reply = _profile_update_reply(session_id)
        return reply, ran_agents
    if name == "start_advice":
        return _start_advice_reply(session_id), False
    if name == "learning_plan":
        return _learning_plan_request_reply(message, intent, session_id)
    if name == "resource_request":
        return _resource_request_reply(message, session_id), True
    if name == "tutoring":
        return _tutoring_reply(message), False
    if name == "progress_feedback":
        return _feedback_reply(message, session_id), False
    if name == "unsafe":
        return "这个请求可能不适合处理。你可以换成正常的学习问题或课程规划需求。", False
    return _unknown_reply(intent), False


# ═══════════════════════════════════════════════════════════════════════
# Chat endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.post("/chat/stream")
def stream_chat(payload: dict[str, Any]) -> StreamingResponse:
    message = str(payload.get("message", "我想学习人工智能导论"))
    session_id = str(payload.get("sessionId", ""))
    if not session_id:
        session_id = "frontend_session_001"

    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message)
    conversation_store.set_intent(session_id, intent)
    reply, ran_agents = _reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", reply)

    def event_stream():
        if ran_agents:
            yield f"data: {json.dumps({'content': '正在启动多智能体协同流程...\n', 'done': False}, ensure_ascii=False)}\n\n"
        else:
            intent_line = f"意图识别：{intent['intent']}（{intent['confidence']:.0%}）\n\n"
            yield f"data: {json.dumps({'content': intent_line, 'done': False}, ensure_ascii=False)}\n\n"
        for chunk in reply.splitlines(keepends=True):
            yield f"data: {json.dumps({'content': chunk, 'done': False}, ensure_ascii=False)}\n\n"
        yield 'data: {"done":true}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/send")
def send_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "我想学习人工智能导论"))
    session_id = str(payload.get("sessionId", ""))
    if not session_id:
        session_id = "frontend_session_001"

    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message)
    conversation_store.set_intent(session_id, intent)
    reply, _ = _reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", reply)
    return {
        "sessionId": session_id,
        "reply": {
            "id": "assistant_msg_001",
            "role": "assistant",
            "content": reply,
            "timestamp": int(time.time() * 1000),
        },
    }


@router.get("/chat/sessions")
def list_sessions() -> dict[str, Any]:
    try:
        db = SessionLocal()
        sessions = repo_list_sessions(db)
        return {
            "sessions": [
                {
                    "id": sess.id,
                    "title": sess.title,
                    "status": sess.status,
                    "createdAt": int(sess.created_at.timestamp() * 1000) if sess.created_at else 0,
                    "updatedAt": int(sess.updated_at.timestamp() * 1000) if sess.updated_at else 0,
                }
                for sess in sessions
            ]
        }
    finally:
        db.close()


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str) -> dict[str, Any]:
    try:
        db = SessionLocal()
        messages = repo_get_messages(db, session_id)
        return {
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
        }
    finally:
        db.close()


@router.post("/chat/sessions/{session_id}/reset")
def reset_session(session_id: str) -> dict[str, Any]:
    conversation_store.reset(session_id)
    return {"ok": True, "sessionId": session_id}


@router.get("/chat/quick-commands")
def quick_commands() -> dict[str, Any]:
    return {
        "commands": [
            {"id": "ai_intro", "label": "AI 入门", "icon": "AI", "prompt": "我是大二学生，想两周入门人工智能"},
            {"id": "nn", "label": "神经网络", "icon": "NN", "prompt": "我想重点学习神经网络，希望多给图解和代码"},
            {"id": "data_structures", "label": "数据结构", "icon": "DS", "prompt": "我是软件工程大二学生，想复习数据结构，为了考试通过"},
        ]
    }


@router.get("/chat/progress/{task_id}")
def generation_progress(task_id: str) -> dict[str, Any]:
    return {"progress": {"stage": "多智能体生成中", "progress": 100, "agentName": "EduAgent", "detail": task_id}}


# ═══════════════════════════════════════════════════════════════════════
# Profile endpoints — read from DB, trigger via POST
# ═══════════════════════════════════════════════════════════════════════


def _resolve_session_id(sessionId: str = "", subjectId: str = "") -> str:
    return sessionId or subjectId or "frontend_session_001"


def _payload_session_id(payload: dict[str, Any]) -> str:
    return str(payload.get("sessionId") or payload.get("subjectId") or "") or "frontend_session_001"


@router.get("/profile")
def get_profile(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Read the latest profile from the database. Never triggers agents."""
    session_id = _resolve_session_id(sessionId, subjectId)

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
            pass
        finally:
            db.close()

        return {
            "profile": {
                "id": session_id,
                "learnerId": learner_id,
                "nickname": nickname,
                "dimensions": _normalize_frontend_dimensions(db_profile.get("dimensions", [])),
                "weaknesses": db_profile.get("weaknesses", []),
                "preferences": {**_default_prefs, **db_prefs},
                "history": {"totalStudyMinutes": 0, "completedTopics": [], "quizAccuracy": None, "streak": 0, "lastStudyDate": 0},
                "createdAt": int(time.time() * 1000) - 86400000,
                "updatedAt": int(time.time() * 1000),
                "source": "db",
                "readiness": readiness,
            }
        }

    # Fall back to in-memory last_result if available (transitional)
    state = conversation_store.get(session_id)
    if state.last_result:
        profile = _to_profile(state.last_result)
        readiness = conversation_store.readiness(state)
        profile["source"] = "agent_generated"
        profile["readiness"] = readiness
        return {"profile": profile}

    # No data at all — return empty structure
    return {"profile": _empty_profile(session_id)}


@router.post("/profile/build")
def build_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger agent pipeline and build/refresh the student profile."""
    session_id = _payload_session_id(payload)
    message = str(payload.get("message", "我想学习人工智能导论"))

    conversation_store.append_message(session_id, "user", message)
    result = _run_agents(message, session_id=session_id)
    profile = _to_profile(result)
    profile["source"] = "agent_generated"

    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    profile["readiness"] = readiness

    return {"profile": profile}


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

    return {"profile": profile}


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
            return {"error": "Learner not found", "learner": None}

        sessions = get_learner_sessions(db, learner_id)
        aggregated = get_learner_aggregated_profile(db, learner_id)

        # Normalize dimensions in aggregated profile
        if aggregated and aggregated.get("dimensions"):
            aggregated["dimensions"] = normalize_profile_dimensions(aggregated["dimensions"])

        return {
            "learner": {
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
            }
        }
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
) -> dict[str, Any]:
    """Read resources from DB. Supports filtering by type/difficulty/source/search."""
    session_id = _resolve_session_id(sessionId, subjectId)

    def _matches(item: dict[str, Any]) -> bool:
        if type and item.get("type", "") != type:
            return False
        if difficulty and item.get("difficulty", "") != difficulty:
            return False
        if source:
            item_source = _source_label(item.get("source", ""))
            if item_source != source:
                return False
        if search:
            q = search.lower()
            title = (item.get("title") or "").lower()
            desc = (item.get("description") or "").lower()
            kps = " ".join(item.get("knowledgePoints", item.get("knowledge_points", []))).lower()
            if q not in title and q not in desc and q not in kps and q not in item.get("id", "").lower():
                return False
        if knowledgePoint:
            kps = item.get("knowledgePoints", item.get("knowledge_points", []))
            if knowledgePoint not in kps:
                return False
        return True
        if type and item.get("type", "") != type:
            return False
        if difficulty and item.get("difficulty", "") != difficulty:
            return False
        if source:
            item_source = _source_label(item.get("source", ""))
            if item_source != source:
                return False
        if search:
            q = search.lower()
            title = (item.get("title") or "").lower()
            desc = (item.get("description") or "").lower()
            kps = " ".join(item.get("knowledgePoints", item.get("knowledge_points", []))).lower()
            if q not in title and q not in desc and q not in kps and q not in item.get("id", "").lower():
                return False
        if knowledgePoint:
            kps = item.get("knowledgePoints", item.get("knowledge_points", []))
            if knowledgePoint not in kps:
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
            "source": _source_label(item.get("source", "")),
            "relatedStageId": item.get("relatedStageId", item.get("related_stage_id", "")),
            "relatedChapter": item.get("relatedChapter", item.get("related_chapter", "")),
            "relatedKnowledgePoints": item.get("relatedKnowledgePoints", item.get("related_knowledge_points", [])),
            "qualityStatus": item.get("qualityStatus", item.get("quality_status", "")),
        }

    # Merge DB resources with in-memory resources.
    # DB resources carry persisted state (study_status, bookmarks).
    # In-memory resources carry full content (title, description, etc.).
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

    # Build in-memory lookup (full content, may lack persisted state)
    memory_map: dict[str, dict[str, Any]] = {}
    if state and state.last_result:
        for item in state.last_result.get("resources", []):
            normalized = _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
            rid = normalized.get("id", "")
            if rid:
                memory_map[rid] = normalized

    # Clean up orphaned DB stubs (created by previous buggy PATCH that saved
    # resources with empty titles). These have no matching memory data and
    # would show garbled content, so remove them from DB.
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
                repo_delete_resource(db, oid)
            db.close()
        except Exception:
            pass
        for oid in orphaned_ids:
            db_map.pop(oid, None)

    # Merge: DB state overlaid on memory content
    all_ids = set(db_map.keys()) | set(memory_map.keys())
    for rid in all_ids:
        db_item = db_map.get(rid)
        mem_item = memory_map.get(rid)
        if db_item and (db_item.get("title") or "").strip() and db_item.get("title") != "学习资源":
            item = db_item  # DB has full content → use as-is
        elif mem_item:
            # Memory has content, DB may have state → merge (carries study_status)
            item = {**mem_item, **(db_item or {})}
            item["id"] = rid
        elif db_item:
            item = db_item  # DB stub only → still show minimally
        else:
            continue
        if _matches(item):
            seen_ids.add(rid)
            merged.append(item)

    # Sort: completed resources to the end
    merged.sort(key=lambda r: 1 if r.get("studyStatus") == "completed" else 0)

    return {"resources": merged, "total": len(merged), "page": 1, "sessionId": session_id}


@router.get("/resources/{resource_id}")
def get_resource(resource_id: str, sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Get a single resource by ID — tries DB first, then in-memory fallback."""
    session_id = _resolve_session_id(sessionId, subjectId)

    # Try DB first
    db_resources = ag_get_resources(session_id)
    db_match = next((r for r in db_resources if r["id"] == resource_id), None)
    if db_match:
        bookmarks = _get_bookmarks(session_id)
        return {"resource": {
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
        }}

    # Fall back to in-memory last_result
    state = conversation_store.get(session_id)
    if state.last_result:
        resources = [
            _to_resource(item, state.last_result.get("course_id", "ai_intro"), session_id)
            for item in state.last_result.get("resources", [])
        ]
        match = next((item for item in resources if item["id"] == resource_id), None)
        if match:
            return {"resource": match}

    return {
        "resource": {
            "id": resource_id,
            "type": "lecture",
            "title": "资源未找到",
            "description": "",
            "content": "",
            "source": "none",
        }
    }


@router.post("/resources/{resource_id}/bookmark")
def bookmark_resource(resource_id: str, sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    try:
        db = SessionLocal()
        # Ensure resource exists in DB before toggling bookmark
        from app.db.repository import save_resource as repo_save_resource
        state = conversation_store.get(session_id)
        if state.last_result:
            for item in state.last_result.get("resources", []):
                if item.get("resource_id") == resource_id:
                    repo_save_resource(db, session_id, {
                        "id": resource_id,
                        "type": item.get("type", "lecture"),
                        "title": item.get("title", "学习资源"),
                        "description": item.get("description", ""),
                        "content": item.get("content", ""),
                    })
                    break
        bookmarked = toggle_bookmark(db, resource_id)
        return {"bookmarked": bookmarked if bookmarked is not None else True}
    finally:
        db.close()


@router.patch("/resources/{resource_id}/study-status")
def update_resource_study_status(resource_id: str, payload: dict[str, Any], sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Update the study status of a resource. Only updates existing DB records."""
    session_id = _resolve_session_id(sessionId, subjectId)
    study_status = str(payload.get("studyStatus", "completed"))
    try:
        db = SessionLocal()
        from app.db.repository import get_resource as repo_get_resource, save_resource as repo_save_resource
        resource = repo_get_resource(db, resource_id)
        if resource:
            # 已有 DB 记录，直接更新状态
            resource.study_status = study_status
            db.commit()
        else:
            # 尚未入库，尝试从内存找完整数据再存
            state = conversation_store.get(session_id)
            if state and state.last_result:
                for item in state.last_result.get("resources", []):
                    rid = item.get("resource_id") or item.get("id", "")
                    if rid == resource_id:
                        repo_save_resource(db, session_id, {
                            "id": resource_id,
                            "type": item.get("type", "lecture"),
                            "title": item.get("title", "学习资源"),
                            "description": item.get("description", ""),
                            "content": item.get("content", ""),
                            "difficulty": item.get("difficulty", "easy"),
                            "source": item.get("source", "agent_generated"),
                            "study_status": study_status,
                        })
                        break
    finally:
        db.close()
    return {"ok": True, "studyStatus": study_status}


@router.post("/resources/generate")
def generate_resource(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger agent pipeline to generate resources for a topic."""
    session_id = _payload_session_id(payload)
    topic = str(payload.get("topic", "学习主题"))
    message = f"请为{topic}生成学习资源"

    result = _run_agents(message, session_id=session_id)
    resources = [
        _to_resource(item, result.get("course_id", "ai_intro"), session_id)
        for item in result.get("resources", [])
    ]
    primary = resources[0] if resources else {"id": "res_new", "title": f"{topic} 个性化资源", "source": "none"}
    return {"resource": primary}


@router.get("/resources/{resource_id}/knowledge-graph")
def resource_knowledge_graph(resource_id: str, sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    session_id = _resolve_session_id(sessionId, subjectId)
    resource = _find_resource_for_graph(resource_id, session_id)
    if not resource:
        return {"mermaidDef": "", "source": "none", "resourceId": resource_id}

    existing = str(resource.get("mermaidDef") or resource.get("mermaid_def") or "").strip()
    if existing:
        return {
            "mermaidDef": existing,
            "source": _source_label(str(resource.get("source", ""))),
            "resourceId": resource_id,
        }

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
    return {
        "mermaidDef": "\n".join(lines),
        "source": _source_label(str(resource.get("source", ""))),
        "resourceId": resource_id,
    }


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
    return {
        "mermaidDef": (
            "mindmap\n"
            "  root((人工智能导论))\n"
            "    机器学习基础\n"
            "    神经网络\n"
            "    自然语言处理\n"
            f"    资源 {resource_id}"
        )
    }


# ── In-memory node progress store ────────────────────────────────────
# Keyed by node_id, stores {status, mastery, updatedAt}
_node_progress_store: dict[str, dict[str, Any]] = {}


def _apply_node_progress(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply saved node progress on top of default stages."""
    for stage in stages:
        for node in stage.get("nodes", []):
            nid = node["id"]
            if nid in _node_progress_store:
                saved = _node_progress_store[nid]
                node["status"] = saved.get("status", node["status"])
                node["mastery"] = saved.get("mastery", node["mastery"])
    return stages


# ═══════════════════════════════════════════════════════════════════════
# Learning path endpoints — read from DB, trigger via POST
# ═══════════════════════════════════════════════════════════════════════


@router.get("/learning-path")
def get_learning_path(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Read the latest learning path from DB. Never triggers agents."""
    session_id = _resolve_session_id(sessionId, subjectId)

    def _build_path(stages: list[dict[str, Any]], base: dict[str, Any]) -> dict[str, Any]:
        stages = _apply_node_progress(stages)
        return {
            "id": base.get("id", f"path_{session_id}"),
            "title": base.get("title", "个性化学习路径"),
            "description": base.get("description", ""),
            "courseName": base.get("courseName", ""),
            "courseId": base.get("courseId", ""),
            "stages": stages,
            "createdAt": base.get("createdAt", int(time.time() * 1000)),
            "overallProgress": 0,
            "estimatedDays": base.get("estimatedDays", 14),
            "source": "agent_generated",
        }

    # Try DB first
    db_path = ag_get_learning_path(session_id)
    if db_path:
        raw_stages = db_path.get("stages", [])
        if isinstance(raw_stages, list):
            stages = _raw_stages_to_nodes(raw_stages)
        else:
            stages = []
        if not stages:
            return {"path": _empty_learning_path(session_id)}
        return {"path": _build_path(stages, {
            "id": db_path.get("id", f"path_{session_id}"),
            "title": f"{db_path.get('course_name', '')}个性化学习路径",
            "description": db_path.get("description", ""),
            "courseName": db_path.get("course_name", ""),
            "courseId": db_path.get("course_id", ""),
            "createdAt": _datetime_to_ms(db_path.get("created_at")),
            "estimatedDays": db_path.get("estimated_days", 14),
        })}

    # Fall back to in-memory last_result
    state = conversation_store.get(session_id)
    if state.last_result:
        path = _to_learning_path(state.last_result)
        if not path.get("stages"):
            return {"path": _empty_learning_path(session_id)}
        path["source"] = "agent_generated"
        path["stages"] = _apply_node_progress(path["stages"])
        return {"path": path}

    return {"path": _empty_learning_path(session_id)}


@router.post("/learning-path/generate")
def generate_learning_path(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger agent pipeline and generate a learning path."""
    session_id = _payload_session_id(payload)

    state = conversation_store.get(session_id)
    message = conversation_store.profile_prompt(state, latest_message="请生成学习路径")
    result = _run_agents(message, session_id=session_id)
    path = _to_learning_path(result)
    return {"path": path}


@router.patch("/learning-path/nodes/{node_id}")
def update_node_progress(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    # 持久化节点进度到内存存储
    _node_progress_store[node_id] = {
        "status": payload.get("status", "available"),
        "mastery": payload.get("mastery", 0),
        "updatedAt": time.time(),
    }
    learning_tracker.log(
        {"event": "node_progress", "resourceId": node_id, "metadata": payload},
        session_id=session_id,
    )
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════
# Feedback & analytics
# ═══════════════════════════════════════════════════════════════════════


@router.post("/feedback")
def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    learning_tracker.log({"event": "feedback", **payload}, session_id=session_id)
    return {"ok": True}


@router.post("/feedback/event")
def log_study_event(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _payload_session_id(payload)
    learning_tracker.log(payload, session_id=session_id)
    return {"ok": True}


@router.get("/learning-analytics")
def learning_analytics(sessionId: str = "", subjectId: str = "") -> dict[str, Any]:
    """Read learning analytics from DB. Never triggers agents."""
    session_id = _resolve_session_id(sessionId, subjectId)

    analytics = ag_get_analytics(session_id)
    return {
        **analytics,
        "summary": "已接入学习事件追踪，可用于后续动态调整画像、资源推荐和学习路径。",
    }
