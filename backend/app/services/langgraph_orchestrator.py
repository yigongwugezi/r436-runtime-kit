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
        }
    except Exception:
        return {"action": "none", "reply": "", "facts": {}}


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
    }, factory)

    state["intent"] = ca_result["action"]
    state["_conversation_reply"] = ca_result["reply"]
    state["_conversation_facts"] = ca_result["facts"]
    state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
    logger.info("Intent: %s", state["intent"])
    return state


async def _conversation_node(state: dict) -> dict:
    """Handle chat-only intents."""
    reply = state.get("_conversation_reply", "")
    if not reply:
        try:
            reply = await deeptutor.chat(
                state.get("user_message", ""),
                state.get("messages", []) or [],
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


async def resume_pipeline_stream(preview_state: dict, factory: AgentFactory | None = None):
    """Resume full_workflow after user confirms preview.

    Runs Phase 2: resource → review → reply.
    Yields the same event types as run_pipeline_stream.
    """
    import time as _time
    if factory is None:
        factory = AgentFactory()
    state: dict[str, Any] = dict(preview_state, _retry_count=0, _factory=factory)

    execute_nodes = ["resource", "review", "reply"]
    try:
        for node_name in execute_nodes:
            meta = _NODE_META.get(node_name, {"agent_name": node_name, "label": node_name})
            t_start = _time.time()
            yield {"type": "agent_progress", "node": node_name,
                   "agent_name": meta["agent_name"], "label": meta["label"],
                   "status": "started"}
            if node_name == "reply":
                await _reply_node(state)
            else:
                await _run_agent(node_name, state, factory)
            card = _result_card(state, node_name) if node_name != "reply" else None
            event: dict[str, Any] = {"type": "agent_progress", "node": node_name,
                   "agent_name": meta["agent_name"], "label": meta["label"],
                   "status": "completed",
                   "duration_ms": int((_time.time() - t_start) * 1000)}
            if card:
                event["card"] = card
            yield event

        # Review → resource retry loop
        retries = 0
        while retries < MAX_RETRIES:
            route = _resolve_retry_route(state)
            if route == "reply":
                break
            retries += 1
            state["_retry_count"] = retries
            yield {"type": "agent_progress", "node": "resource",
                   "agent_name": "ResourceAgent", "label": "生成学习资源",
                   "status": "retrying", "retry": retries,
                   "max_retries": MAX_RETRIES,
                   "reason": "资源质量未通过审查"}
            t_start = _time.time()
            await _run_agent("resource", state, factory)
            yield {"type": "agent_progress", "node": "resource",
                   "agent_name": "ResourceAgent", "label": "生成学习资源",
                   "status": "completed",
                   "card": _result_card(state, "resource"),
                   "duration_ms": int((_time.time() - t_start) * 1000)}
            t_start = _time.time()
            await _run_agent("review", state, factory)
            yield {"type": "agent_progress", "node": "review",
                   "agent_name": "ReviewAgent", "label": "质量审查",
                   "status": "completed",
                   "card": _result_card(state, "review"),
                   "duration_ms": int((_time.time() - t_start) * 1000)}

        # Structured cards
        for node_name in ("resource", "review"):
            card = _result_card(state, node_name)
            if card:
                yield {"type": "structured_output", "node": node_name, "card": card}

    except Exception as exc:
        logger.error("Resume pipeline error: %s", exc)
        yield {"type": "error", "message": str(exc)}

    state["pipeline_executed"] = True
    state["overall_status"] = "completed"
    if retries >= MAX_RETRIES:
        state["quality_status"] = "warning"

    reply = state.get("final_reply", "") or "学习流程已完成"
    yield {"type": "final_reply", "content": reply}

    diagnosis = state.get("diagnosis", {})
    review = state.get("review", {}) if isinstance(state.get("review"), dict) else {}
    path = state.get("learning_path") or state.get("stages") or []
    yield {"type": "nav_state", "badges": _nav_badges(diagnosis, review, path)}

    yield {**dict(state), "type": "done"}


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
        }, factory)
        intent = ca_result["action"]
        state["intent"] = intent
        state["_conversation_reply"] = ca_result["reply"]

    # ── Chat-only intents (no agent execution needed) ──
    if intent in chat_only_intents():
        reply = state.get("_conversation_reply", "")
        if not reply:
            try:
                reply = await deeptutor.chat(
                    state.get("user_message", ""), state.get("messages", []) or [],
                )
            except Exception:
                reply = "你好！我是EduAgent，有什么可以帮你的？"
        state["final_reply"] = reply or "你好！我是EduAgent，有什么可以帮你的？"
        state["pipeline_executed"] = True
        state["overall_status"] = "completed"
        return dict(state)

    # ── Single-agent shortcut ──
    agent_ids = get_agent_ids(intent)
    if agent_ids is not None and len(agent_ids) > 0:
        # Map agent_id → short node key (e.g. "planner_agent" → "planner")
        for full_id in agent_ids:
            short_key = full_id.replace("_agent", "")
            if factory.has(full_id):
                await _run_agent(short_key, state, factory)

        state["pipeline_executed"] = True
        state["overall_status"] = "completed"

        # Build a reasonable final_reply for single-agent runs
        path = state.get("learning_path", [])
        resources = state.get("resources", [])
        questions = state.get("questions", [])
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
        return dict(state)

    # ── Full workflow ──
    graph = build_unified_graph().compile()
    result = await graph.ainvoke(state, {"recursion_limit": 50})
    result["pipeline_executed"] = True
    result["overall_status"] = "completed"
    retries = result.get("_retry_count", 0)
    if retries >= MAX_RETRIES:
        result["quality_status"] = "warning"
    return dict(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Streaming pipeline — yields AgentProgressEvent dicts for SSE
# ═══════════════════════════════════════════════════════════════════════════════

# Node → Agent metadata for progress events
_NODE_META: dict[str, dict[str, str]] = {
    "intent_router":  {"agent_name": "ConversationAgent", "label": "分析意图"},
    "conversation":   {"agent_name": "ConversationAgent", "label": "生成回复"},
    "profile":        {"agent_name": "ProfileAgent",      "label": "提取学习画像"},
    "knowledge":      {"agent_name": "KnowledgeAgent",    "label": "检索知识库"},
    "diagnosis":      {"agent_name": "DiagnosisAgent",    "label": "诊断薄弱点"},
    "planner":        {"agent_name": "PlannerAgent",      "label": "规划学习路径"},
    "resource":       {"agent_name": "ResourceAgent",     "label": "生成学习资源"},
    "question":       {"agent_name": "QuestionAgent",     "label": "生成练习题"},
    "review":         {"agent_name": "ReviewAgent",       "label": "质量审查"},
    "grading":        {"agent_name": "GradingAgent",      "label": "批改答案"},
    "reply":          {"agent_name": "ConversationAgent", "label": "汇总结果"},
}


def _result_card(state: dict, node: str) -> dict[str, Any]:
    """Extract a structured summary card from agent output for frontend rendering.

    Returns a dict with at minimum ``{summary, card_type, data}``.
    The frontend uses ``card_type`` to pick the right card component.
    """
    if node == "profile":
        profile = state.get("profile", {})
        if isinstance(profile, dict):
            dims = []
            for k, v in profile.items():
                if isinstance(v, dict):
                    dims.append({"key": k, "label": v.get("label", k),
                                 "value": v.get("value", ""), "score": v.get("score", 0),
                                 "confidence": v.get("confidence", 0), "source": v.get("source", "")})
            filled = [d for d in dims if d["value"] and d["value"] != "待补充"]
            return {"summary": f"已填充 {len(filled)}/9 个维度", "card_type": "profile_update",
                    "data": {"dimensions": dims, "filled_count": len(filled), "total": 9}}

    if node == "knowledge":
        ctx = state.get("knowledge_context", {})
        pts = ctx.get("retrieved_points", [])
        return {"summary": f"检索到 {len(pts)} 个知识点", "card_type": "knowledge_context",
                "data": {"course_name": ctx.get("course_name", ""),
                         "points": [{"name": p.get("name", ""), "priority": p.get("priority", ""),
                                     "difficulty": p.get("difficulty", "")} for p in pts[:8]],
                         "source": ctx.get("source", "")}}

    if node == "diagnosis":
        diag = state.get("diagnosis", {})
        weak = diag.get("weak_knowledge_points") or diag.get("weak_topics") or []
        return {"summary": f"识别 {len(weak)} 个薄弱点", "card_type": "diagnosis_result",
                "data": {"weak_points": [{"name": w.get("name") or w.get("topic", ""),
                         "priority": w.get("priority", ""), "confidence": w.get("confidence", 0)}
                        for w in weak[:5]],
                         "high_count": sum(1 for w in weak if w.get("priority") == "high"),
                         "overall_confidence": diag.get("confidence", 0),
                         "needs_more_evidence": diag.get("needs_more_evidence", False),
                         "risk_flags": diag.get("risk_flags", [])}}

    if node == "planner":
        path = state.get("learning_path") or state.get("stages") or []
        return {"summary": f"生成 {len(path)} 个学习阶段", "card_type": "learning_path_preview",
                "data": {"stages": [{"stage_id": s.get("stage_id", ""), "title": s.get("title", ""),
                         "duration": s.get("duration", ""), "estimated_days": s.get("estimated_days", 0),
                         "tasks": s.get("tasks", [])} for s in path],
                         "estimated_days": state.get("estimatedDays", 0),
                         "review_count": len(state.get("review_tasks", [])),
                         "risk_flags": state.get("risk_flags", [])}}

    if node == "resource":
        resources = state.get("resources") or []
        return {"summary": f"生成 {len(resources)} 个资源", "card_type": "resources_ready",
                "data": {"resources": [{"resource_id": r.get("resource_id", ""),
                         "type": r.get("type", ""), "title": r.get("title", ""),
                         "quality_status": r.get("quality_status", ""),
                         "related_stage_id": r.get("related_stage_id", "")}
                        for r in resources],
                         "by_type": _count_by_type(resources),
                         "by_quality": _count_by_quality(resources)}}

    if node == "question":
        questions = state.get("questions") or []
        return {"summary": f"生成 {len(questions)} 道题", "card_type": "questions_ready",
                "data": {"questions": [{"question_id": q.get("question_id", ""),
                         "type": q.get("type", ""), "stem": str(q.get("stem", ""))[:100],
                         "difficulty": q.get("difficulty", "")} for q in questions[:10]],
                         "count": len(questions)}}

    if node == "review":
        review = state.get("review", {})
        checks = review.get("checks", [])
        return {"summary": review.get("summary", ""), "card_type": "review_result",
                "data": {"quality_status": review.get("quality_status", ""),
                         "checks": [{"check_id": c.get("check_id", ""), "label": c.get("label", ""),
                                     "status": c.get("status", "")} for c in checks],
                         "passed": sum(1 for c in checks if c.get("status") == "passed"),
                         "warning": sum(1 for c in checks if c.get("status") == "warning"),
                         "blocked": sum(1 for c in checks if c.get("status") == "blocked")}}

    if node == "grading":
        grade = state.get("grading_result", {})
        return {"summary": f"得分: {grade.get('total_score', '-')}/100", "card_type": "grading_result",
                "data": {"total_score": grade.get("total_score", 0),
                         "error_type": grade.get("error_type", ""),
                         "error_label": grade.get("error_label", ""),
                         "dimension_scores": grade.get("dimension_scores", {}),
                         "suggestions": grade.get("suggestions", [])}}

    if node == "reply":
        return {"summary": state.get("final_reply", ""), "card_type": "final_reply",
                "data": {"reply": state.get("final_reply", "")}}

    return {"summary": "完成", "card_type": "generic", "data": {}}


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


def _nav_badges(diagnosis: dict, review: dict, path: list) -> dict[str, Any]:
    """Compute left-nav badge counts from agent outputs."""
    weak = diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []
    weak_high = sum(1 for w in weak if w.get("priority") == "high")
    review_checks = review.get("checks", [])
    review_warnings = sum(1 for c in review_checks if c.get("status") == "warning")
    review_blocked = sum(1 for c in review_checks if c.get("status") == "blocked")
    return {
        "diagnosis_weak_count": len(weak),
        "diagnosis_high_count": weak_high,
        "path_has_new": len(path) > 0,
        "review_warning_count": review_warnings,
        "review_blocked_count": review_blocked,
        "profile_filled": 0,  # populated by frontend from profile card
    }


async def run_pipeline_stream(**kwargs):
    """Async generator: run pipeline and yield progress events.

    Each yield is a dict meant to be serialized as an SSE event::

        {"type": "agent_progress", "node": "...", "status": "started", ...}
        {"type": "agent_progress", "node": "...", "status": "completed", ...}
        {"type": "final_reply", "content": "..."}
        {"type": "done", ...}

    The final yield is the complete state dict with ``type: "done"``.
    """
    import time as _time
    factory = AgentFactory()
    state: dict[str, Any] = dict(**kwargs, _retry_count=0, _factory=factory)

    # ── Intent classification ──
    t0 = _time.time()
    intent = state.get("intent", "")
    if not intent:
        yield {"type": "agent_progress", "node": "intent_router",
               "agent_name": "ConversationAgent", "label": "分析意图",
               "status": "started"}
        ca_result = await _run_conversation_agent({
            "user_message": state.get("user_message", ""),
            "profile_facts": state.get("profile_facts", {}),
            "conversation_history": state.get("messages", []),
        }, factory)
        intent = ca_result["action"]
        state["intent"] = intent
        state["_conversation_reply"] = ca_result["reply"]
        yield {"type": "agent_progress", "node": "intent_router",
               "agent_name": "ConversationAgent", "label": "分析意图",
               "status": "completed", "summary": f"意图: {intent}",
               "duration_ms": int((_time.time() - t0) * 1000)}

    # ── Chat-only ──
    if intent in chat_only_intents():
        reply = state.get("_conversation_reply", "")
        if not reply:
            try:
                reply = await deeptutor.chat(state.get("user_message", ""), state.get("messages", []) or [])
            except Exception:
                reply = "你好！我是EduAgent，有什么可以帮你的？"
        state["final_reply"] = reply or "你好！我是EduAgent，有什么可以帮你的？"
        state["pipeline_executed"] = True
        state["overall_status"] = "completed"
        if reply:
            yield {"type": "final_reply", "content": reply}
        yield {**dict(state), "type": "done"}
        return

    # ── Single-agent shortcut ──
    agent_ids = get_agent_ids(intent)
    if agent_ids is not None and len(agent_ids) > 0:
        for full_id in agent_ids:
            short_key = full_id.replace("_agent", "")
            if not factory.has(full_id):
                continue
            meta = _NODE_META.get(short_key, {"agent_name": short_key, "label": short_key})
            t_start = _time.time()
            yield {"type": "agent_progress", "node": short_key,
                   "agent_name": meta["agent_name"], "label": meta["label"],
                   "status": "started"}
            await _run_agent(short_key, state, factory)
            yield {"type": "agent_progress", "node": short_key,
                   "agent_name": meta["agent_name"], "label": meta["label"],
                   "status": "completed",
                   "card": _result_card(state, short_key),
                   "duration_ms": int((_time.time() - t_start) * 1000)}

        state["pipeline_executed"] = True
        state["overall_status"] = "completed"
        reply = state.get("final_reply", "") or _diagnosis_reply(state.get("diagnosis")) or "处理完成"
        if reply:
            yield {"type": "final_reply", "content": reply}
        yield {**dict(state), "type": "done"}
        return

    # ── Full workflow — Phase 1: preview (profile→knowledge→diagnosis→planner) ──
    preview_nodes = ["intent_router", "profile", "knowledge", "diagnosis", "planner"]
    for node_name in preview_nodes:
        if node_name == "intent_router":
            continue  # intent already classified above
        if not factory.has(f"{node_name}_agent"):
            continue
        meta = _NODE_META.get(node_name, {"agent_name": node_name, "label": node_name})
        t_start = _time.time()
        yield {"type": "agent_progress", "node": node_name,
               "agent_name": meta["agent_name"], "label": meta["label"],
               "status": "started"}
        await _run_agent(node_name, state, factory)
        card = _result_card(state, node_name)
        yield {"type": "agent_progress", "node": node_name,
               "agent_name": meta["agent_name"], "label": meta["label"],
               "status": "completed",
               "card": card,
               "duration_ms": int((_time.time() - t_start) * 1000)}

    # Yield structured cards for center area
    for node_name in ("diagnosis", "planner"):
        card = _result_card(state, node_name)
        if card:
            yield {"type": "structured_output", "node": node_name, "card": card}

    # ── Yield preview for user confirmation ──
    planner_card = _result_card(state, "planner")
    yield {"type": "preview_ready",
           "planner": planner_card,
           "diagnosis": _result_card(state, "diagnosis"),
           "profile": _result_card(state, "profile"),
           "session_id": state.get("session_id", "")}

    # ── Pause here — frontend calls POST /api/chat/confirm to resume ──
    # Store state in conversation_store so resume can pick it up
    state["_preview_phase"] = "awaiting_confirmation"
    state["_preview_state"] = dict(state)  # snapshot for resume
    # Strip non-serializable stuff
    state["_preview_state"].pop("_factory", None)
    state["_preview_state"].pop("messages", None)
    yield {**dict(state), "type": "awaiting_confirmation",
           "message": "预览已生成，请确认或调整方案后继续"}
