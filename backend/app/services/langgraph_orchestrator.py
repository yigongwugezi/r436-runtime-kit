"""Unified LangGraph orchestrator — intent routing + pipeline + feedback loop (async)."""

from __future__ import annotations

import asyncio
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
        "knowledge": KnowledgeAgent(mock_data={}, llm_client=llm),
        "diagnosis": DiagnosisAgent(mock_data={}, llm_client=llm),
        "planner": PlannerAgent(mock_data={}, llm_client=llm),
        "resource": ResourceAgent(mock_data={}, llm_client=llm),
        "question": QuestionAgent(mock_data={}, llm_client=llm),
        "review": ReviewAgent(mock_data={}, llm_client=llm),
        "grading": GradingAgent(mock_data={}, llm_client=llm),
    }


async def _run_agent(agent_id: str, state: dict) -> dict:
    agents = _make_agents()
    agent = agents[agent_id]
    ctx = dict(state)
    ctx["_retry_count"] = state.get("_retry_count", 0)
    result = await asyncio.to_thread(agent.run, ctx)
    for k, v in result.items():
        if k != "agent_step":
            state[k] = v
    state.setdefault("agent_steps", []).append(result.get("agent_step", {}))
    return state


async def _intent_node(state: dict) -> dict:
    if state.get("intent") in ("full_workflow",):
        state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
        return state
    from app.agents.conversation_agent import ConversationAgent
    ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
    context = {"user_message": state.get("user_message",""), "profile_facts": state.get("profile_facts",{}), "conversation_history": state.get("messages",[])}
    try:
        result = await asyncio.to_thread(ca.run, context)
        state["intent"] = result.get("action", "none")
        state["_conversation_reply"] = result.get("reply", "")
        state["_conversation_facts"] = result.get("facts", {})
    except Exception:
        state["intent"] = "none"
    state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
    logger.info("Intent: %s", state["intent"])
    return state


async def _conversation_node(state: dict) -> dict:
    from app.agents.conversation_agent import ConversationAgent
    ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
    reply = state.get("_conversation_reply", "")
    if not reply:
        try:
            reply = await asyncio.to_thread(ca._try_deeptutor_reply, state.get("user_message",""), state.get("messages",[]) or [])
        except Exception:
            reply = "你好！我是EduAgent学习助手，有什么可以帮你的？"
    state["final_reply"] = reply or "你好！我是EduAgent学习助手，有什么可以帮你的？"
    state.setdefault("agent_steps", []).append({"node": "conversation"})
    return state


async def _reply_node(state: dict) -> dict:
    from app.agents.conversation_agent import ConversationAgent
    ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
    path = state.get("learning_path") or []
    resources = state.get("resources") or []
    parts = []
    if path: parts.append(f"已生成{len(path)}个学习阶段")
    if resources: parts.append(f"配套{len(resources)}个资源")
    summary = "、".join(parts) if parts else "生成流程已完成"
    try:
        reply = await asyncio.to_thread(ca._try_deeptutor_reply, f"后端执行完成：{summary}。请用自然语气告知学生结果。", state.get("messages",[]) or [])
        state["final_reply"] = reply or summary
    except Exception:
        state["final_reply"] = summary
    state.setdefault("agent_steps", []).append({"node": "reply"})
    return state


async def _profile_node(state: dict) -> dict: return await _run_agent("profile", state)
async def _knowledge_node(state: dict) -> dict: return await _run_agent("knowledge", state)
async def _diagnosis_node(state: dict) -> dict: return await _run_agent("diagnosis", state)
async def _plan_node(state: dict) -> dict: return await _run_agent("planner", state)
async def _question_node(state: dict) -> dict:
    """Question node — delegate entirely to QuestionAgent (handles DeepTutor internally)."""
    return await _run_agent("question", state)

async def _resource_node(state: dict) -> dict:
    """Resource node — delegate entirely to ResourceAgent (handles DeepTutor internally)."""
    return await _run_agent("resource", state)

async def _review_node(state: dict) -> dict: return await _run_agent("review", state)
async def _grading_node(state: dict) -> dict: return await _run_agent("grading", state)


def _route_by_intent(state: dict) -> str:
    intent = state.get("intent", "none")
    return {"none":"conversation","tutoring":"conversation","unsafe":"conversation","profile":"profile",
            "plan":"planner","resources":"resource","generate_questions":"question","diagnose":"diagnosis",
            "grade_answer":"grading","full_workflow":"pipeline_start"}.get(intent, "conversation")


def _after_review(state: dict) -> str:
    """Route based on review results: loop back to resource if quality fails and retries remain."""
    review = state.get("review", {})
    quality_status = review.get("quality_status", "passed")

    if quality_status in ("blocked", "failed"):
        checks = review.get("checks", [])
        resource_issues = any(
            c.get("check_id") in (
                "resource_content_quality", "resource_coverage",
                "resource_type_match", "semantic_quality",
            )
            and c.get("status") in ("blocked", "warning")
            for c in checks
        )
        if resource_issues:
            retries = state.get("_retry_count", 0)
            if retries < MAX_RETRIES:
                state["_retry_count"] = retries + 1
                logger.info(
                    "Review flagged resource issues (retry %d/%d), looping back",
                    state["_retry_count"], MAX_RETRIES,
                )
                return "resource"

    return "reply"


def build_unified_graph() -> StateGraph:
    g = StateGraph(dict)
    g.set_entry_point("intent_router")
    for name, node in [("intent_router",_intent_node),("conversation",_conversation_node),("reply",_reply_node),
                       ("profile",_profile_node),("knowledge",_knowledge_node),("diagnosis",_diagnosis_node),
                       ("planner",_plan_node),("resource",_resource_node),("question",_question_node),
                       ("review",_review_node),("grading",_grading_node)]:
        g.add_node(name, node)
    g.add_conditional_edges("intent_router", _route_by_intent, {"conversation":"conversation","profile":"profile",
        "planner":"planner","resource":"resource","question":"question","diagnosis":"diagnosis","grading":"grading","pipeline_start":"profile"})
    g.add_edge("conversation", END); g.add_edge("reply", END)
    g.add_edge("profile","knowledge"); g.add_edge("knowledge","diagnosis")
    g.add_edge("diagnosis","planner"); g.add_edge("planner","resource")
    g.add_edge("resource","review")
    g.add_conditional_edges("review", _after_review, {"reply":"reply","resource":"resource"})
    return g


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

    parts = [summary or "\u5df2\u5b8c\u6210\u8584\u5f31\u70b9\u8bca\u65ad\u3002"]
    if weak_points:
        parts.append("\u91cd\u70b9\u5173\u6ce8\uff1a" + "\u3001".join(weak_points) + "\u3002")
    if next_actions:
        parts.append("\u4e0b\u4e00\u6b65\u5efa\u8bae\uff1a" + "\uff1b".join(next_actions) + "\u3002")
    return "".join(parts)


async def run_pipeline(**kwargs) -> dict[str, Any]:
    state = dict(**kwargs, _retry_count=0)
    intent = state.get("intent", "")
    if not intent:
        from app.agents.conversation_agent import ConversationAgent
        ca = ConversationAgent(mock_data={}, llm_client=get_llm_client(settings.llm_provider))
        try:
            result = await asyncio.to_thread(ca.run, {"user_message": state.get("user_message",""), "profile_facts": state.get("profile_facts",{}), "conversation_history": state.get("messages",[])})
            intent = result.get("action", "none")
            state["intent"] = intent; state["_conversation_reply"] = result.get("reply","")
        except Exception:
            intent = "none"; state["intent"] = "none"

    if intent in ("none", "tutoring", ""):
        reply = state.get("_conversation_reply", "")
        if not reply:
            try:
                from app.services.deeptutor_client import deeptutor_call_async
                reply = await deeptutor_call_async("chat", state.get("user_message",""), state.get("messages",[]))
            except Exception:
                reply = "你好！我是EduAgent，有什么可以帮你的？"
        state["final_reply"] = reply or "你好！我是EduAgent，有什么可以帮你的？"
        state["pipeline_executed"] = True; state["overall_status"] = "completed"
        return dict(state)

    single_map = {"plan":"planner","resources":"resource","generate_questions":"question","diagnose":"diagnosis","grade_answer":"grading"}
    node = single_map.get(intent)
    if node:
        result = await _run_agent(node, state)
        result["pipeline_executed"] = True; result["overall_status"] = "completed"
        path = result.get("learning_path",[]); resources = result.get("resources",[]); questions = result.get("questions",[])
        summary_parts = []
        if path: summary_parts.append(f"已生成{len(path)}个学习阶段")
        if resources: summary_parts.append(f"配套{len(resources)}个学习资源")
        if questions: summary_parts.append(f"生成{len(questions)}道练习题")
        diagnosis_reply = _diagnosis_reply(result.get("diagnosis")) if node == "diagnosis" else ""
        if diagnosis_reply:
            result["final_reply"] = diagnosis_reply
        elif summary_parts:
            result["final_reply"] = "\u3001".join(summary_parts) + "\u3002"
        return dict(result)

    graph = build_unified_graph().compile()
    result = await graph.ainvoke(state, {"recursion_limit": 50})
    result["pipeline_executed"] = True; result["overall_status"] = "completed"
    retries = result.get("_retry_count", 0)
    if retries >= MAX_RETRIES: result["quality_status"] = "warning"
    return dict(result)
