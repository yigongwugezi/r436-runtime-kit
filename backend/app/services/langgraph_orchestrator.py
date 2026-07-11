"""Unified LangGraph orchestrator — intent routing + pipeline + feedback loop (async).

Refactored (Phase 2):
  - AgentFactory replaces _make_agents() → lazy, shared LLM client
  - IntentRouter replaces 3 scattered intent→agent maps → single source of truth
  - Single ConversationAgent per request via factory cache
  - DeepTutorFacade replaces scattered deeptutor_call calls
  - Generalized RetryPolicy replaces hardcoded _after_review
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.base import get_agent_class
from app.services.agent_factory import AgentFactory
from app.services.intent_router import (
    get_node_route, get_agent_ids, should_run_agents,
    chat_only_intents,
)
from app.services.deeptutor_facade import deeptutor

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


# ═══════════════════════════════════════════════════════════════════════════════
# Profile context helpers — shared between conversation node and ConversationAgent
# ═══════════════════════════════════════════════════════════════════════════════

_LABEL_MAP = {
    "background": "专业/年级",
    "target_course": "想学的课程",
    "knowledge_base": "已有基础",
    "weak_points": "薄弱点",
    "learning_goal": "学习目标",
    "time_budget": "时间安排",
    "preference": "学习偏好",
}


def _build_profile_context(facts: dict[str, str]) -> str:
    """Build a natural-language student-profile summary for DeepTutor's memory_context."""
    parts: list[str] = []
    for key, label in _LABEL_MAP.items():
        value = str(facts.get(key, "")).strip()
        if value and value not in ("未提及", "待补充", "未知", "", "无"):
            parts.append(f"{label}：{value}")
    if not parts:
        return ""
    return (
        "【学生画像——仅供你了解学生，不要在回复中逐条复述这些信息，"
        "而是在对话中自然地融入你对学生的了解】\n" + "\n".join(parts)
    )


def _summarize_known_facts(facts: dict[str, str]) -> str:
    """One-line summary of what we know about the student."""
    parts = []
    for key, label in _LABEL_MAP.items():
        val = str(facts.get(key, "")).strip()
        if val and val not in ("未提及", "待补充", "未知", "", "无"):
            parts.append(f"{label}={val}")
    return "；".join(parts) if parts else "暂无"


def _build_chat_persona(facts: dict[str, str]) -> str:
    """Build persona instructions that override DeepTutor's default tutor persona.

    Tells DeepTutor to act as a friendly profile-gathering assistant rather
    than a tutor who asks templated questions.  Injected via persona_context
    which DeepTutor eagerly places in the system prompt.
    """
    filled = {k for k, v in facts.items() if v and str(v).strip() and str(v).strip() not in ("未提及", "待补充", "未知", "", "无")}
    total = len(_LABEL_MAP)
    missing_labels = [_LABEL_MAP[k] for k in _LABEL_MAP if k not in filled]
    filled_pct = len(filled) / max(1, total)

    if filled_pct == 0:
        return (
            "你是一个友善、健谈的学习助手。正在第一次认识学生。"
            "热情地打个招呼,然后了解学生想学什么。不要用 | 分隔问题。不要模板句式。"
        )
    elif filled_pct < 0.3:
        # 1-2 facts: start with basics
        known_list = "、".join(_LABEL_MAP[k] for k in filled) if filled else "几乎什么都不了解"
        return (
            "你是一个细心、善于提问的学习助手。刚开始了解这个学生。"
            f"目前只知道:{known_list}。"
            "不要急着推进——先把这个学生的情况摸清楚。"
            "比如学生说想学某门课,就追问'之前接触过吗?是完全零基础还是有一定了解?';"
            "不要只收一个词就满意,要让学生展开说。"
            "每次只聊一个话题,但要聊透。不要用 | 分隔问题。不要模板句式。"
        )
    elif filled_pct < 0.5:
        # 3-4 facts: dig deeper, ask "why" and "how"
        known_list = "、".join(_LABEL_MAP[k] for k in filled)
        missing = "/".join(missing_labels[:2]) if missing_labels else ""
        return (
            "你是一个追根究底的学习助手。已经了解到一些基本信息了,"
            f"但每个维度都还可以深挖。已知:{known_list}。还需要了解:{missing}。"
            "对已有的每一条信息,都可以追问'为什么'和'怎么样':"
            "- '我学过导数' → '学到什么程度?复合函数求导会吗?隐函数呢?'"
            "- '期末考高分' → '大概什么时候?之前考过类似的吗?感觉哪块最难?'"
            "- '每天3小时' → '是连续的还是分散的?周末呢?'"
            "不要同时问多个维度,但一个维度要聊到有具体信息为止。不要用 |。不要模板。"
        )
    elif filled_pct < 0.7:
        # 5 facts: cross-reference and find contradictions
        known_list = "、".join(_LABEL_MAP[k] for k in filled)
        missing = "/".join(missing_labels) if missing_labels else ""
        return (
            "你是一个洞察力强的学习助手。情况了解得差不多了,"
            f"但还可以更精准。已知:{known_list}。缺口:{missing}。"
            "现在要做的是交叉验证和细化——把笼统的信息变成具体的:"
            "- '薄弱点:积分' → '是不定积分不会,还是定积分应用搞不懂?换元法和分部积分哪个更吃力?'"
            "- '两周' → '每天能学多久?只有工作日还是包括周末?'"
            "- 如果还没问学习偏好,现在一定要问:是喜欢看视频、读教材、还是刷题?'"
            "不要跳到'要不要生成'——还没到那一步。继续聊,把缺口补上。不要模板。"
        )
    elif filled_pct < 0.9:
        # 6 facts: last gap, very specific
        missing_str = "/".join(missing_labels) if missing_labels else ""
        return (
            "你是一个精益求精的学习助手。就差最后一点了——{missing_str}。"
            "不要敷衍地问,要结合已有的信息设计一个针对性的问题。"
            "比如已经知道学生学微积分、时间紧、积分弱,那最后问学习偏好时要结合场景:"
            "'你觉得听课和自己看书哪个效果好?要不要我给你配一些视频?'"
            "只问这一个,但要让问题有上下文。问完这次就差不多可以生成了。不要模板。"
        )
    else:
        # 7+ facts: ALL filled, now suggest
        course = str(facts.get("target_course", ""))
        is_lang = any(w in course for w in ["英语","日语","韩语","法语","德语","语言","雅思","托福"])
        mode_hint = ""
        if course:
            mode_hint = (
                "学生的画像已经非常完整了。自然地总结一下你了解到的信息,"
                "让学生确认对不对,然后输出模式选择标签:\n"
                "[[mode-pick:教材式,日课式,精进式|course:{course}|default:"
                + ("日课式" if is_lang else "教材式") +
                "]]\n"
                "输出标签后不要再说别的选择文字。"
            )
        return (
            "你是一个用心、准备充分的学习助手。画像全部到位了。"
            + mode_hint +
            "先简要回顾你了解到的学生情况(让学生确认),再问要不要生成。不要催促。"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Retry policy — generalized from the old hardcoded _after_review
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RetryPolicy:
    """Per-agent retry policy for quality-feedback loops."""
    max_retries: int = 2
    retry_on_check_ids: tuple[str, ...] = ()
    retry_node: str = ""          # which LangGraph node to loop back to
    notify_upstream: tuple[str, ...] = ()  # nodes to notify on retry (future use)


# Default policies — easily extensible
RETRY_POLICIES: dict[str, RetryPolicy] = {
    "resource": RetryPolicy(
        max_retries=2,
        retry_on_check_ids=(
            "resource_content_quality", "resource_coverage",
            "resource_type_match", "semantic_quality",
        ),
        retry_node="resource",
        notify_upstream=("planner",),
    ),
}


def _resolve_retry_route(state: dict) -> str:
    """Generalized post-review routing.

    Iterates over RETRY_POLICIES and loops back to the first matching
    agent node that hasn't exceeded its retry budget.
    """
    review = state.get("review", {})
    quality_status = review.get("quality_status", "passed")
    if quality_status not in ("blocked", "failed"):
        return "reply"

    checks = review.get("checks", [])
    for agent_node, policy in RETRY_POLICIES.items():
        has_issues = any(
            c.get("check_id") in policy.retry_on_check_ids
            and c.get("status") in ("blocked", "warning")
            for c in checks
        )
        if has_issues:
            retries = state.get("_retry_count", 0)
            if retries < policy.max_retries:
                state["_retry_count"] = retries + 1
                logger.info(
                    "Review flagged %s issues (retry %d/%d), looping back to %s",
                    agent_node, state["_retry_count"], policy.max_retries, policy.retry_node,
                )
                return policy.retry_node

    return "reply"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent execution helpers
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_agent(agent_id: str, state: dict, factory: AgentFactory) -> dict:
    """Run a single agent by its short key (e.g. "planner", "resource")."""
    full_agent_id = f"{agent_id}_agent"  # short key → agent_id convention
    agent = factory.get(full_agent_id)
    if agent is None:
        logger.error("Unknown agent: %s", agent_id)
        state.setdefault("agent_steps", []).append({"node": agent_id, "error": "unknown_agent"})
        return state
    ctx = dict(state)
    ctx["_retry_count"] = state.get("_retry_count", 0)
    result = await asyncio.to_thread(agent.run, ctx)
    for k, v in result.items():
        if k != "agent_step":
            state[k] = v
    state.setdefault("agent_steps", []).append(result.get("agent_step", {}))
    return state


async def _run_conversation_agent(context: dict[str, Any], factory: AgentFactory) -> dict[str, Any]:
    """Run ConversationAgent once and cache the result.

    Uses the factory so the same LLM client + cached instance is used
    across intent / conversation / reply nodes within a single request.
    """
    ca = factory.get("conversation_agent")
    if ca is None:
        return {"action": "none", "reply": "", "facts": {}}
    try:
        result = await asyncio.to_thread(ca.run, context)
        return {
            "action": str(result.get("action", "none")),
            "reply": str(result.get("reply", "")),
            "facts": result.get("facts", {}),
            "plan_mode": str(result.get("plan_mode", "")),
            "path_mode": str(result.get("path_mode", "")),
        }
    except Exception:
        return {"action": "none", "reply": "", "facts": {}, "plan_mode": "", "path_mode": ""}


def _emit_feedback_signal(state: dict) -> dict[str, Any]:
    """Extract FeedbackSignal from grading results for the next request cycle.

    Returns a dict with a ``feedback_signal`` key (or empty dict) suitable
    for merging into the pipeline return value.  The signal is consumed by
    ConversationAgent on the *next* request.
    """
    grading = state.get("grading_result") or {}
    if not isinstance(grading, dict):
        return {}
    error_type = str(grading.get("error_type", "")).strip()
    if not error_type or error_type == "null":
        return {}
    from app.schemas.feedback import FeedbackSignal
    signal = FeedbackSignal.from_grading_result(grading)
    return {"feedback_signal": signal}


# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph nodes
# ═══════════════════════════════════════════════════════════════════════════════


async def _intent_node(state: dict) -> dict:
    """Classify user intent via ConversationAgent (once, cached in factory)."""
    factory: AgentFactory = state.get("_factory")
    if factory is None:
        state.setdefault("agent_steps", []).append({"node": "intent_router", "error": "no_factory"})
        state["intent"] = "none"
        return state

    # If intent already provided by upstream caller, skip classification
    if state.get("intent") in ("full_workflow",):
        state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
        return state

    ca_result = await _run_conversation_agent({
        "user_message": state.get("user_message", ""),
        "profile_facts": state.get("profile_facts", {}),
        "conversation_history": state.get("messages", []),
        "feedback_signal": state.get("feedback_signal"),
    }, factory)

    state["intent"] = ca_result["action"]
    state["_conversation_reply"] = ca_result["reply"]
    state["_conversation_facts"] = ca_result["facts"]
    plan_mode = ca_result.get("plan_mode", "")
    if plan_mode:
        state["plan_mode"] = plan_mode
    state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
    logger.info("Intent: %s", state["intent"])
    return state


async def _conversation_node(state: dict) -> dict:
    """Handle chat-only intents."""
    msg = state.get("user_message", "")
    reply = state.get("_conversation_reply", "")

    # Video/animation → native async DeepTutor
    if any(kw in msg for kw in ["视频","动画","微课","短片"]):
        try:
            reply = await deeptutor.chat(
                f"为'{msg}'生成教学视频脚本。包含片头、核心讲解场景、片尾。标注时间轴。2000字以上。",
                state.get("messages", []) or [],
            )
            if reply and len(reply) > 100:
                state["final_reply"] = reply
                state.setdefault("agent_steps", []).append({"node": "conversation_video"})
                return state
        except Exception:
            pass

    if not reply:
        try:
            # ── Build profile context for DeepTutor ──
            profile_facts = state.get("profile_facts", {}) or {}
            profile_context = _build_profile_context(profile_facts)
            persona_context = _build_chat_persona(profile_facts)

            reply = await deeptutor.chat(
                msg, state.get("messages", []) or [],
                profile_context=profile_context,
                persona_context=persona_context,
            )
        except Exception:
            reply = ""
    state["final_reply"] = reply or "你好！我是EduAgent学习助手，有什么可以帮你的？"
    state.setdefault("agent_steps", []).append({"node": "conversation"})
    return state


async def _reply_node(state: dict) -> dict:
    """Summarize pipeline results in natural language."""
    path = state.get("learning_path") or []
    resources = state.get("resources") or []
    parts = []
    if path:
        parts.append(f"已生成{len(path)}个学习阶段")
    if resources:
        parts.append(f"配套{len(resources)}个资源")
    summary = "、".join(parts) if parts else "生成流程已完成"
    try:
        reply = await deeptutor.chat(
            f"后端执行完成：{summary}。请用自然语气告知学生结果。",
            state.get("messages", []) or [],
        )
        state["final_reply"] = reply or summary
    except Exception:
        state["final_reply"] = summary
    state.setdefault("agent_steps", []).append({"node": "reply"})
    return state


# ── Pipeline agent nodes ──────────────────────────────────────────────


async def _profile_node(state: dict) -> dict:
    return await _run_agent("profile", state, state["_factory"])

async def _knowledge_node(state: dict) -> dict:
    return await _run_agent("knowledge", state, state["_factory"])

async def _diagnosis_node(state: dict) -> dict:
    return await _run_agent("diagnosis", state, state["_factory"])

async def _plan_node(state: dict) -> dict:
    return await _run_agent("planner", state, state["_factory"])

async def _resource_node(state: dict) -> dict:
    return await _run_agent("resource", state, state["_factory"])

async def _question_node(state: dict) -> dict:
    return await _run_agent("question", state, state["_factory"])

async def _review_node(state: dict) -> dict:
    return await _run_agent("review", state, state["_factory"])

async def _grading_node(state: dict) -> dict:
    return await _run_agent("grading", state, state["_factory"])


# ═══════════════════════════════════════════════════════════════════════════════
# Graph construction — uses IntentRouter for edge definitions
# ═══════════════════════════════════════════════════════════════════════════════


def _route_by_intent(state: dict) -> str:
    """Route from intent_router → the appropriate LangGraph node."""
    return get_node_route(state.get("intent", "none"))


def build_unified_graph() -> StateGraph:
    """Build the full LangGraph state graph.

    Node names and edge targets are derived from IntentRouter so that
    adding a new intent only requires updating intent_router.py.
    """
    g = StateGraph(dict)
    g.set_entry_point("intent_router")

    # All possible nodes
    nodes = [
        ("intent_router", _intent_node),
        ("conversation", _conversation_node),
        ("reply", _reply_node),
        ("profile", _profile_node),
        ("knowledge", _knowledge_node),
        ("diagnosis", _diagnosis_node),
        ("planner", _plan_node),
        ("resource", _resource_node),
        ("question", _question_node),
        ("review", _review_node),
        ("grading", _grading_node),
    ]
    for name, fn in nodes:
        g.add_node(name, fn)

    # Conditional edges from intent_router → all possible targets
    # "pipeline_start" is an alias that redirects to "profile" (the first full-workflow node)
    edge_targets = {
        "conversation": "conversation",
        "profile": "profile",
        "knowledge": "knowledge",
        "planner": "planner",
        "resource": "resource",
        "question": "question",
        "diagnosis": "diagnosis",
        "grading": "grading",
        "pipeline_start": "profile",
    }
    g.add_conditional_edges("intent_router", _route_by_intent, edge_targets)

    # Terminal / chat edges
    g.add_edge("conversation", END)
    g.add_edge("reply", END)

    # NOTE: "question" and "grading" nodes are intentionally NOT in the full-workflow
    # pipeline edges below. They are reached only via the single-agent shortcut path
    # (intent_router → run_pipeline single-agent branch). This is by design:
    # question generation and grading are on-demand actions triggered by explicit
    # user intent, not automatic pipeline stages.
    #
    # Pipeline edges (fixed order for full_workflow)
    g.add_edge("profile", "knowledge")
    g.add_edge("knowledge", "diagnosis")
    g.add_edge("diagnosis", "planner")
    g.add_edge("planner", "resource")
    g.add_edge("resource", "review")
    g.add_conditional_edges("review", _resolve_retry_route, {"reply": "reply", "resource": "resource"})

    return g


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════


def _stringify_items(items: Any, limit: int = 3) -> list[str]:
    if not isinstance(items, list):
        return []
    values: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            value = item.get("topic") or item.get("knowledge_point") or item.get("name") or item.get("title") or item.get("label")
        else:
            value = item
        value = str(value or "").strip()
        if value:
            values.append(value)
    return values


def _diagnosis_reply(diagnosis: Any) -> str:
    if not isinstance(diagnosis, dict):
        return ""
    summary = str(diagnosis.get("diagnosis_summary") or diagnosis.get("summary") or "").strip()
    weak_points = _stringify_items(diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics"))
    next_actions = _stringify_items(diagnosis.get("recommended_next_actions") or diagnosis.get("next_actions"), limit=2)
    parts = [summary or "已完成薄弱点诊断。"]
    if weak_points:
        parts.append("重点关注：" + "、".join(weak_points) + "。")
    if next_actions:
        parts.append("下一步建议：" + "；".join(next_actions) + "。")
    return "".join(parts)


async def run_pipeline(**kwargs) -> dict[str, Any]:
    """Run the full agent pipeline (or single-agent shortcut).

    This is the single entry point called by agent_service and chat_router.
    Internally it uses AgentFactory for lazy agent creation and IntentRouter
    for intent → agent mapping.
    """
    factory = AgentFactory()
    state: dict[str, Any] = dict(**kwargs, _retry_count=0, _factory=factory)

    # ── Intent classification (if not already provided) ──
    intent = state.get("intent", "")
    if not intent:
        ca_result = await _run_conversation_agent({
            "user_message": state.get("user_message", ""),
            "profile_facts": state.get("profile_facts", {}),
            "conversation_history": state.get("messages", []),
            "feedback_signal": state.get("feedback_signal"),
        }, factory)
        intent = ca_result["action"]
        state["intent"] = intent
        state["_conversation_reply"] = ca_result["reply"]
        plan_mode = ca_result.get("plan_mode", "")
        path_mode = ca_result.get("path_mode", "")
        if plan_mode:
            state["plan_mode"] = plan_mode
        if path_mode:
            state["path_mode"] = path_mode

    # ── Chat-only intents (no agent execution needed) ──
    if intent in chat_only_intents():
        profile_facts = state.get("profile_facts", {}) or {}
        profile_context = _build_profile_context(profile_facts)
        persona_context = _build_chat_persona(profile_facts)
        logger.info(
            "Chat intent=%s session=%s facts=%d ctx_len=%d",
            intent, state.get("session_id", "?"),
            sum(1 for v in profile_facts.values() if v and str(v).strip()),
            len(profile_context),
        )
        reply = ""
        try:
            reply = await deeptutor.chat(
                state.get("user_message", ""),
                state.get("messages", []) or [],
                profile_context=profile_context,
                persona_context=persona_context,
            )
        except Exception:
            reply = ""
        state["final_reply"] = reply or "你好！我是EduAgent，有什么可以帮你的？"
        state["pipeline_executed"] = True
        state["overall_status"] = "completed"
        return dict(state)

    # ── Single-agent shortcut ──
    # If agents_filter is explicitly provided (from product.py multi-action dispatch),
    # use it directly; otherwise derive agent_ids from intent.
    agents_filter = state.pop("agents_filter", None)
    agent_ids = agents_filter if (agents_filter is not None and len(agents_filter) > 0) else get_agent_ids(intent)
    if agent_ids is not None and len(agent_ids) > 0:
        # Snapshot old results so we only report what's newly generated
        old_path = len(state.get("learning_path") or [])
        old_res = len(state.get("resources") or [])
        old_qs = len(state.get("questions") or [])

        # Map agent_id → short node key (e.g. "planner_agent" → "planner")
        for full_id in agent_ids:
            short_key = full_id.replace("_agent", "")
            if factory.has(full_id):
                await _run_agent(short_key, state, factory)

        state["pipeline_executed"] = True
        state["overall_status"] = "completed"

        # Only report newly generated data (not stale from previous requests)
        path = (state.get("learning_path") or [])[old_path:] if old_path > 0 else state.get("learning_path") or []
        resources = (state.get("resources") or [])[old_res:] if old_res > 0 else state.get("resources") or []
        questions = (state.get("questions") or [])[old_qs:] if old_qs > 0 else state.get("questions") or []
        summary_parts = []
        if path:
            summary_parts.append(f"已生成{len(path)}个学习阶段")
        if resources:
            summary_parts.append(f"配套{len(resources)}个学习资源")
        if questions:
            summary_parts.append(f"生成{len(questions)}道练习题")
        diag_reply = _diagnosis_reply(state.get("diagnosis")) if "diagnosis" in intent else ""
        if diag_reply:
            state["final_reply"] = diag_reply
        elif summary_parts:
            state["final_reply"] = "、".join(summary_parts) + "。"
        fb = _emit_feedback_signal(state)
        if fb:
            state.update(fb)
        return dict(state)

    # ── Full workflow ──
    graph = build_unified_graph().compile()
    result = await graph.ainvoke(state, {"recursion_limit": 50})
    result["pipeline_executed"] = True
    result["overall_status"] = "completed"
    retries = result.get("_retry_count", 0)
    if retries >= MAX_RETRIES:
        result["quality_status"] = "warning"
    fb = _emit_feedback_signal(result)
    if fb:
        result.update(fb)
    return dict(result)
