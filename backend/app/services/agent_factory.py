"""Lazy Agent Factory — single LLM client, on-demand agent creation.

Replaces the scatter-shot ``_make_agents()`` pattern in langgraph_orchestrator
(which created all 8 agents + 1 LLM client per node invocation).

Usage::

    factory = AgentFactory()
    profile_agent = factory.get("profile")      # creates ProfileAgent + LLM client on first call
    profile_agent2 = factory.get("profile")      # returns cached instance
    planner_agent = factory.get("planner")       # creates PlannerAgent, reuses same LLM client
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent, get_agent_class
from app.config import settings
from app.services.llm_client import BaseLLMClient, get_llm_client


class AgentFactory:
    """Creates and caches agent instances for the lifetime of one pipeline run.

    - Exactly **one** ``BaseLLMClient`` is created and shared across all agents.
    - Agents are instantiated lazily on first ``get()`` and cached.
    - ConversationAgent is NOT managed here (it has its own lifecycle via
      ``from_context()`` — though that too is unified in Phase 2).
    """

    def __init__(self, llm_client: BaseLLMClient | None = None) -> None:
        self._llm: BaseLLMClient | None = llm_client
        self._instances: dict[str, BaseAgent] = {}

    @property
    def llm(self) -> BaseLLMClient | None:
        """The shared LLM client (lazy-init from settings on first access)."""
        if self._llm is None:
            self._llm = get_llm_client(settings.llm_provider)
        return self._llm

    def get(self, agent_id: str) -> BaseAgent | None:
        """Return a cached agent instance for *agent_id*, creating it if needed.

        Args:
            agent_id: The ``agent_id`` class attribute of the agent (e.g. ``"planner_agent"``).

        Returns:
            The agent instance, or *None* if the ``agent_id`` is not registered.
        """
        if agent_id not in self._instances:
            cls = get_agent_class(agent_id)
            if cls is None:
                return None
            # DI: DiagnosisAgent receives a QuestionAgent factory to break hard coupling
            if agent_id == "diagnosis_agent":
                self._instances[agent_id] = cls(
                    mock_data={}, llm_client=self.llm,
                    question_agent_factory=lambda: self.get("question_agent"),
                )
            else:
                self._instances[agent_id] = cls(mock_data={}, llm_client=self.llm)
        return self._instances[agent_id]

    def get_or_fallback(self, agent_id: str) -> BaseAgent:
        """Like :meth:`get` but raises ``KeyError`` on unknown agent ids."""
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent_id: {agent_id!r}")
        return agent

    def has(self, agent_id: str) -> bool:
        """Check whether *agent_id* is registered (class exists, not instance)."""
        return get_agent_class(agent_id) is not None

    def clear(self) -> None:
        """Discard all cached instances (useful for testing)."""
        self._instances.clear()
        self._llm = None
