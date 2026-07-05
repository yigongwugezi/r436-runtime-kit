"""LangGraph-based orchestrator with review feedback loops."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from operator import add

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


# ── State: use flat dict with reducer for the retry counter ──


def _retry_reducer(left: int, right: int) -> int:
    return max(left, right)


# Use plain dict — LangGraph copies dict subclasses incorrectly


# ── Nodes ──


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


def _profile_node(state: dict) -> dict:
    return _run_agent("profile", state)


def _knowledge_node(state: dict) -> dict:
    return _run_agent("knowledge", state)


def _diagnosis_node(state: dict) -> dict:
    return _run_agent("diagnosis", state)


def _plan_node(state: dict) -> dict:
    return _run_agent("planner", state)


def _resource_node(state: dict) -> dict:
    # Try DeepTutor for mindmap and research resources
    try:
        from app.services.deeptutor_client import generate_mindmap, generate_research
        course = state.get("course_id", "") or "当前课程"
        # Generate mindmap via DeepTutor
        mm = generate_mindmap(course)
        # Generate research material
        rm = generate_research(course)
        # Inject into state as additional resources
        extra = []
        if mm:
            extra.append({"resource_id": "dt_mindmap", "type": "mindmap", "title": f"{course}思维导图",
                          "content": mm, "related_stage_id": "stage_1", "source": "deeptutor",
                          "format": "mermaid", "difficulty": "medium", "quality_status": "passed"})
        if rm:
            extra.append({"resource_id": "dt_research", "type": "reading", "title": f"{course}拓展阅读",
                          "content": rm, "related_stage_id": "stage_1", "source": "deeptutor",
                          "format": "markdown", "difficulty": "medium", "quality_status": "passed"})
        if extra:
            state.setdefault("resources", [])
            state["resources"] = (state.get("resources") or []) + extra
    except Exception:
        pass
    return _run_agent("resource", state)


def _question_node(state: dict) -> dict:
    # Try DeepTutor for quiz generation
    try:
        from app.services.deeptutor_client import generate_quiz
        course = state.get("course_id", "") or "当前课程"
        qs = generate_quiz(course, "", 5)
        if qs:
            state.setdefault("questions", [])
            state["questions"] = [
                {"question_id": "dt_q1", "type": "mixed", "stem": qs, "source": "deeptutor"}
            ]
    except Exception:
        pass
    return _run_agent("question", state)


def _review_node(state: dict) -> dict:
    return _run_agent("review", state)


# ── Routing ──


def _after_review(state: dict) -> str:
    retries = state.get("_retry_count", 0)
    review_data = state.get("review", {})
    passed = review_data.get("quality_status") == "passed" if isinstance(review_data, dict) else False

    if passed:
        logger.info("Review PASSED")
        return "end"

    if retries >= MAX_RETRIES:
        logger.warning("Review failed after %d retries, accepting with warnings", retries)
        return "end"

    # IMPORTANT: increment retry BEFORE returning so the next call sees it
    retries += 1
    state["_retry_count"] = retries
    logger.info("Review retry %d/%d → back to resource", retries, MAX_RETRIES)
    return "resource"


# ── Graph ──


def build_graph() -> StateGraph:
    g = StateGraph(dict)

    g.add_node("profile", _profile_node)
    g.add_node("knowledge", _knowledge_node)
    g.add_node("diagnosis", _diagnosis_node)
    g.add_node("planner", _plan_node)
    g.add_node("resource", _resource_node)
    g.add_node("review", _review_node)

    g.set_entry_point("profile")
    g.add_edge("profile", "knowledge")
    g.add_edge("knowledge", "diagnosis")
    g.add_edge("diagnosis", "planner")
    g.add_edge("planner", "resource")
    g.add_edge("resource", "review")

    g.add_conditional_edges("review", _after_review, {
        "end": END,
        "resource": "resource",
    })

    return g


def run_pipeline(**kwargs) -> dict[str, Any]:
        agents_filter = kwargs.pop("agents_filter", None)
        state = dict(**kwargs, _retry_count=0)

        # Single-agent mode: trigger one agent directly
        if agents_filter and len(agents_filter) == 1:
            agent_id = agents_filter[0]
            node_map = {"profile_agent": "profile", "knowledge_agent": "knowledge",
                        "diagnosis_agent": "diagnosis", "planner_agent": "planner",
                        "resource_agent": "resource", "question_agent": "question",
                        "review_agent": "review", "grading_agent": "grading"}
            node = node_map.get(agent_id)
            if node:
                result = _run_agent(node, state)
                result["pipeline_executed"] = True
                result["overall_status"] = "completed"
                return dict(result)

        # Full pipeline with review loop
        graph = build_graph().compile()
        result = graph.invoke(state, {"recursion_limit": 25})
        result["pipeline_executed"] = True
        result["overall_status"] = "completed"
        retries = result.get("_retry_count", 0)
        if retries >= MAX_RETRIES:
            result["quality_status"] = "warning"
            result["reason"] = "部分资源经过多轮修改仍存在问题"
        return dict(result)
