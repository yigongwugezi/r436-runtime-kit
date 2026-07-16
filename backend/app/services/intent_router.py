"""Unified Intent Router — single source of truth for intent → agent plan mapping.

Replaces the three scattered intent-mapping sites:
  1. ``langgraph_orchestrator._route_by_intent()``  — intent → LangGraph node name
  2. ``langgraph_orchestrator.run_pipeline()``       — intent → agent key (single_map)
  3. ``product._agents_for_action()``                — action → agent_id list

All intent routing now queries this module.  Adding a new action requires
only ONE change here — the three consumers pick up the mapping automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class AgentPlan:
    """What agents to run for a given intent."""

    # Agent agent_id strings needed to fulfil this intent.
    # ``None`` means "run the full pipeline" (the orchestrator decides which).
    agent_ids: list[str] | None

    # LangGraph node route key (e.g. "planner", "resource") for single-agent intents.
    # Set to "conversation" for chat-only intents, "pipeline_start" for full_workflow.
    node_route: str = "conversation"

    # Whether this action triggers actual agent execution (vs. pure chat).
    should_run_agents: bool = False

    # Whether this action runs ALL agents in the standard pipeline.
    is_full_workflow: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# The Registry — single source of truth
# ═══════════════════════════════════════════════════════════════════════════════

INTENT_REGISTRY: dict[str, AgentPlan] = {
    # ── Chat-only intents (no agents executed) ──
    "none":      AgentPlan(agent_ids=[],  node_route="conversation",  should_run_agents=False),
    "tutoring":  AgentPlan(agent_ids=["profile_agent", "diagnosis_agent", "resource_agent"], node_route="profile", should_run_agents=True),
    "unsafe":    AgentPlan(agent_ids=[],  node_route="conversation",  should_run_agents=False),
    "":           AgentPlan(agent_ids=[],  node_route="conversation",  should_run_agents=False),

    # ── Single-agent intents ──
    "profile":            AgentPlan(agent_ids=["profile_agent"],     node_route="profile",     should_run_agents=True),
    "plan":               AgentPlan(agent_ids=["planner_agent"],     node_route="planner",     should_run_agents=True),
    "resources":          AgentPlan(agent_ids=["resource_agent"],    node_route="resource",    should_run_agents=True),
    "generate_questions": AgentPlan(agent_ids=["question_agent"],    node_route="question",    should_run_agents=True),
    "diagnose":           AgentPlan(agent_ids=["diagnosis_agent"],   node_route="diagnosis",   should_run_agents=True),
    "grade_answer":       AgentPlan(agent_ids=["grading_agent"],     node_route="grading",     should_run_agents=True),
    "knowledge":          AgentPlan(agent_ids=["knowledge_agent"],   node_route="knowledge",   should_run_agents=True),

    # ── Combined multi-agent intents (closed-loop) ──
    "assess": AgentPlan(
        agent_ids=["grading_agent", "diagnosis_agent", "profile_agent", "planner_agent", "resource_agent"],
        node_route="grading",
        should_run_agents=True,
    ),
    "tutor": AgentPlan(
        agent_ids=["profile_agent", "diagnosis_agent", "resource_agent", "multimodal_agent"],
        node_route="profile",
        should_run_agents=True,
    ),

    "tutoring": AgentPlan(
        agent_ids=["profile_agent", "diagnosis_agent", "resource_agent", "multimodal_agent"],
        node_route="profile",
        should_run_agents=True,
    ),
    "full_workflow": AgentPlan(
        agent_ids=None,
        node_route="pipeline_start",
        should_run_agents=True,
        is_full_workflow=True,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Lookup helpers — used by orchestrator & product router
# ═══════════════════════════════════════════════════════════════════════════════


def get_plan(intent: str) -> AgentPlan:
    """Return the :class:`AgentPlan` for *intent*, falling back to ``"none"``."""
    return INTENT_REGISTRY.get(intent) or INTENT_REGISTRY["none"]


def get_node_route(intent: str) -> str:
    """Return the LangGraph node route key for *intent*."""
    return get_plan(intent).node_route


def get_agent_ids(intent: str) -> list[str] | None:
    """Return the list of ``agent_id`` strings for *intent*.

    Returns *None* for ``full_workflow`` (meaning "run all").
    Returns an empty list for chat-only intents.
    """
    return get_plan(intent).agent_ids


def should_run_agents(intent: str) -> bool:
    """Return *True* if this intent requires agent execution."""
    return get_plan(intent).should_run_agents


def is_full_workflow(intent: str) -> bool:
    """Return *True* if this intent triggers the full agent pipeline."""
    return get_plan(intent).is_full_workflow


def all_agent_ids() -> list[str]:
    """Return every ``agent_id`` referenced across all registered intents."""
    ids: set[str] = set()
    for plan in INTENT_REGISTRY.values():
        if plan.agent_ids:
            ids.update(plan.agent_ids)
    return sorted(ids)


def chat_only_intents() -> set[str]:
    """Return the set of intents that do NOT trigger agent execution."""
    return {k for k, v in INTENT_REGISTRY.items() if not v.should_run_agents}
