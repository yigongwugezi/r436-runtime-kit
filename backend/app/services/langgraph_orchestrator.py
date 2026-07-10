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
