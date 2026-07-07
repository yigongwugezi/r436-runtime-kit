"""Unified LangGraph orchestrator — intent routing + pipeline + feedback loop."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents import (
    DiagnosisAgent, GradingAgent, KnowledgeAgent,
    PlannerAgent, ProfileAgent, QuestionAgent, ResourceAgent, ReviewAgent,
)
from app.config import settings
from app.services.llm_client import get_llm_client

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def _make_agents():
    llm = get_llm_client(settings.llm_provider)
    return {
        "profile": ProfileAgent(mock_data={}, llm_client=llm),
        "knowledge": KnowledgeAgent(mock_data={}),
        "diagnosis": DiagnosisAgent(mock_data={}, llm_client=llm),
        "planner": PlannerAgent(mock_data={}, llm_client=llm),
        "resource": ResourceAgent(mock_data={}, llm_client=llm),
        "question": QuestionAgent(mock_data={}, llm_client=llm),
        "review": ReviewAgent(mock_data={}),
        "grading": GradingAgent(mock_data={}, llm_client=llm),
    }


def _run_agent(agent_id: str, state: dict) -> dict:
    agents = _make_agents()
    agent = agents[agent_id]
    ctx = dict(state)
    ctx["_retry_count"] = state.get("_retry_count", 0)
    result = agent.run(ctx)
    for k, v in result.items():
        if k != "agent_step":
            state[k] = v
    state.setdefault("agent_steps", []).append(result.get("agent_step", {}))
    return state


# ── Unified Graph Nodes ──

def _intent_node(state: dict) -> dict:
    """Classify intent via ConversationAgent rules + LLM."""
    # Skip if intent already determined (e.g., full_workflow from pre-graph routing)
    if state.get("intent") in ("full_workflow",):
        state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
        return state
    from app.agents.conversation_agent import ConversationAgent
    ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
    context = {
        "user_message": state.get("user_message", ""),
        "profile_facts": state.get("profile_facts", {}),
        "conversation_history": state.get("messages", []),
    }
    try:
        result = ca.run(context)
        state["intent"] = result.get("action", "none")
        state["_conversation_reply"] = result.get("reply", "")
        state["_conversation_facts"] = result.get("facts", {})
    except Exception:
        state["intent"] = "none"
    state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
    logger.info("Intent: %s", state["intent"])
    return state


def _conversation_node(state: dict) -> dict:
    """Handle casual/tutoring conversation via DeepTutor."""
    from app.agents.conversation_agent import ConversationAgent
    ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
    reply = state.get("_conversation_reply", "")
    if not reply:
        reply = ca._try_deeptutor_reply(
            state.get("user_message", ""),
            state.get("messages", []) or [],
        ) or "你好！我是EduAgent学习助手，有什么可以帮你的？"
    state["final_reply"] = reply
    state.setdefault("agent_steps", []).append({"node": "conversation"})
    return state


def _reply_node(state: dict) -> dict:
    """Generate final reply after pipeline execution."""
    from app.agents.conversation_agent import ConversationAgent
    ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
    path = state.get("learning_path") or []
    resources = state.get("resources") or []
    parts = []
    if path:
        parts.append(f"已生成{len(path)}个学习阶段")
    if resources:
        parts.append(f"配套{len(resources)}个资源")
    summary = "、".join(parts) if parts else "生成流程已完成"
    try:
        reply = ca._try_deeptutor_reply(
            f"后端执行完成：{summary}。请用自然语气告知学生结果，不要模板话术。",
            state.get("messages", []) or [],
        ) or summary
    except Exception:
        reply = summary
    state["final_reply"] = reply
    state.setdefault("agent_steps", []).append({"node": "reply"})
    return state


# ── Pipeline Nodes ──

def _profile_node(state: dict) -> dict:
    return _run_agent("profile", state)


def _knowledge_node(state: dict) -> dict:
    return _run_agent("knowledge", state)


def _diagnosis_node(state: dict) -> dict:
    return _run_agent("diagnosis", state)


def _plan_node(state: dict) -> dict:
    return _run_agent("planner", state)


def _resource_node(state: dict) -> dict:
    return _run_agent("resource", state)


def _question_node(state: dict) -> dict:
    return _run_agent("question", state)


def _review_node(state: dict) -> dict:
    return _run_agent("review", state)


def _grading_node(state: dict) -> dict:
    return _run_agent("grading", state)


# ── Routing ──

def _route_by_intent(state: dict) -> str:
    intent = state.get("intent", "none")
    route_map = {
        "none": "conversation",
        "tutoring": "conversation",
        "unsafe": "conversation",
        "profile": "profile",
        "plan": "planner",
        "resources": "resource",
        "generate_questions": "question",
        "diagnose": "diagnosis",
        "grade_answer": "grading",
        "full_workflow": "pipeline_start",
    }
    return route_map.get(intent, "conversation")


def _after_review(state: dict) -> str:
    retries = state.get("_retry_count", 0)
    review_data = state.get("review", {})
    passed = review_data.get("quality_status") == "passed" if isinstance(review_data, dict) else False
    if passed or retries >= MAX_RETRIES:
        return "reply"
    state["_retry_count"] = retries + 1
    return "resource"


# ── Unified Graph ──

def build_unified_graph() -> StateGraph:
    g = StateGraph(dict)
    g.set_entry_point("intent_router")

    # All nodes
    g.add_node("intent_router", _intent_node)
    g.add_node("conversation", _conversation_node)
    g.add_node("reply", _reply_node)
    g.add_node("profile", _profile_node)
    g.add_node("knowledge", _knowledge_node)
    g.add_node("diagnosis", _diagnosis_node)
    g.add_node("planner", _plan_node)
    g.add_node("resource", _resource_node)
    g.add_node("question", _question_node)
    g.add_node("review", _review_node)
    g.add_node("grading", _grading_node)

    # Intent routing
    g.add_conditional_edges("intent_router", _route_by_intent, {
        "conversation": "conversation",
        "profile": "profile",
        "planner": "planner",
        "resource": "resource",
        "question": "question",
        "diagnosis": "diagnosis",
        "grading": "grading",
        "pipeline_start": "profile",
    })

    # Terminal
    g.add_edge("conversation", END)
    g.add_edge("reply", END)

    # Pipeline path: profile → knowledge → diagnosis → planner → resource ⇄ review → reply
    g.add_edge("profile", "knowledge")
    g.add_edge("knowledge", "diagnosis")
    g.add_edge("diagnosis", "planner")
    g.add_edge("planner", "resource")
    g.add_edge("resource", "review")
    g.add_conditional_edges("review", _after_review, {
        "reply": "reply",
        "resource": "resource",
    })

    return g


def run_pipeline(**kwargs) -> dict[str, Any]:
    state = dict(**kwargs, _retry_count=0)

    # Classify intent first (needed for both modes)
    intent = state.get("intent", "")
    if not intent:
        from app.agents.conversation_agent import ConversationAgent
        ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
        try:
            result = ca.run({"user_message": state.get("user_message", ""), "profile_facts": state.get("profile_facts", {}), "conversation_history": state.get("messages", [])})
            intent = result.get("action", "none")
            state["intent"] = intent
            state["_conversation_reply"] = result.get("reply", "")
        except Exception:
            intent = "none"
            state["intent"] = "none"

    # Single-agent mode: intent routed directly, no pipeline
    single_map = {"plan": "planner", "resources": "resource",
                  "generate_questions": "question", "diagnose": "diagnosis",
                  "grade_answer": "grading", "none": None, "tutoring": None}
    # Conversation: return DeepTutor reply directly
    if intent in ("none", "tutoring", ""):
        reply = state.get("_conversation_reply", "")
        if not reply:
            from app.services.deeptutor_client import deeptutor_call
            reply = deeptutor_call("chat", state.get("user_message", ""),
                                   state.get("messages", [])) or "你好！我是EduAgent，有什么可以帮你的？"
        state["final_reply"] = reply
        state["pipeline_executed"] = True
        state["overall_status"] = "completed"
        return dict(state)

    node = single_map.get(intent)
    if node:
        result = _run_agent(node, state)
        result["pipeline_executed"] = True
        result["overall_status"] = "completed"
        # Generate reply for single-agent results
        path = result.get("learning_path", [])
        resources = result.get("resources", [])
        questions = result.get("questions", [])
        summary_parts = []
        if path: summary_parts.append(f"已生成{len(path)}个学习阶段")
        if resources: summary_parts.append(f"配套{len(resources)}个学习资源")
        if questions: summary_parts.append(f"生成{len(questions)}道练习题")
        if summary_parts:
            result["final_reply"] = "、".join(summary_parts) + "。你可以到对应页面查看详细内容。"
        return dict(result)

    # Full pipeline for full_workflow
    graph = build_unified_graph().compile()
    result = graph.invoke(state, {"recursion_limit": 50})
    result["pipeline_executed"] = True
    result["overall_status"] = "completed"
    return dict(result)
