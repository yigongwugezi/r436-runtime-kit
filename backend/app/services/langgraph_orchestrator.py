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
        "knowledge": KnowledgeAgent(mock_data={}),
        "diagnosis": DiagnosisAgent(mock_data={}, llm_client=llm),
        "planner": PlannerAgent(mock_data={}, llm_client=llm),
        "resource": ResourceAgent(mock_data={}, llm_client=llm),
        "question": QuestionAgent(mock_data={}, llm_client=llm),
        "review": ReviewAgent(mock_data={}),
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
async def _resource_node(state: dict) -> dict: return await _run_agent("resource", state)
async def _question_node(state: dict) -> dict:
    """Question node — try DeepTutor deep_question capability first."""
    try:
        from app.services.deeptutor_client import deeptutor_call_async
        course = state.get("course_id","") or "当前课程"
        msg = state.get("user_message","")
        r = await deeptutor_call_async("deep_question", f"为'{course}'生成练习题。需求：{msg}")
        if r and len(r) > 50:
            import uuid, json
            try:
                s, e = r.find("{"), r.rfind("}")+1
                qs = json.loads(r[s:e]).get("questions",[]) if s>=0 and e>s else []
            except: qs = [{"question_id":f"dt_{uuid.uuid4().hex[:8]}","type":"mixed","stem":r[:500],"source":"deeptutor_deep_question"}]
            if qs:
                state["questions"] = qs
                state.setdefault("agent_steps",[]).append({"agent_id":"question_agent","status":"completed"})
                return state
    except Exception: pass
    return await _run_agent("question", state)

async def _resource_node(state: dict) -> dict:
    """Resource node — try DeepTutor visualize capability first."""
    try:
        from app.services.deeptutor_client import deeptutor_call_async
        course = state.get("course_id","") or "当前课程"
        # Try visualize for mindmap
        r = await deeptutor_call_async("visualize", f"为'{course}'生成思维导图，用Mermaid格式")
        if r and len(r) > 50 and 'mermaid' in r.lower():
            import uuid
            state.setdefault("resources",[])
            state["resources"].append({"resource_id":uuid.uuid4().hex[:12],"type":"mindmap","title":f"{course}思维导图","content":r,"source":"deeptutor_visualize","format":"mermaid","quality_status":"passed"})
            state.setdefault("agent_steps",[]).append({"agent_id":"resource_agent","status":"completed"})
            return state
    except Exception: pass
    return await _run_agent("resource", state)

async def _review_node(state: dict) -> dict: return await _run_agent("review", state)
async def _grading_node(state: dict) -> dict: return await _run_agent("grading", state)


def _route_by_intent(state: dict) -> str:
    intent = state.get("intent", "none")
    return {"none":"conversation","tutoring":"conversation","unsafe":"conversation","profile":"profile",
            "plan":"planner","resources":"resource","generate_questions":"question","diagnose":"diagnosis",
            "grade_answer":"grading","full_workflow":"pipeline_start"}.get(intent, "conversation")


def _after_review(state: dict) -> str:
    retries = state.get("_retry_count", 0)
    review_data = state.get("review", {})
    passed = review_data.get("quality_status") == "passed" if isinstance(review_data, dict) else False
    if passed or retries >= MAX_RETRIES: return "reply"
    state["_retry_count"] = retries + 1
    return "resource"


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
        if summary_parts: result["final_reply"] = "、".join(summary_parts) + "。"
        return dict(result)

    graph = build_unified_graph().compile()
    result = await graph.ainvoke(state, {"recursion_limit": 50})
    result["pipeline_executed"] = True; result["overall_status"] = "completed"
    retries = result.get("_retry_count", 0)
    if retries >= MAX_RETRIES: result["quality_status"] = "warning"
    return dict(result)
