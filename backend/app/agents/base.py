"""Common agent contract with validation, fallback, and error handling.

All stage agents inherit from BaseAgent.  The contract now supports:

- Optional ``mock_data`` for explicit local demos only.
- ``validate_result()`` — override to enforce required output fields.
- ``get_fallback()`` — safe defaults returned when the agent fails or times out.
- ``@register_agent`` — decorator-based auto-registration (replaces manual __init__.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.services.llm_client import BaseLLMClient


# ═══════════════════════════════════════════════════════════════════════════════
# Global Agent Registry — single source of truth for agent discovery
# ═══════════════════════════════════════════════════════════════════════════════

_AGENT_REGISTRY: dict[str, type["BaseAgent"]] = {}


def register_agent(cls=None, *, agent_id: str | None = None):
    """Decorator that registers an agent class in the global registry.

    Can be used as ``@register_agent`` (reads ``cls.agent_id``) or
    ``@register_agent(agent_id="custom_id")`` for explicit naming.

    Registered agents are discoverable via :func:`get_registered_agents`
    and :func:`get_agent_class`.
    """
    def _wrap(c: type["BaseAgent"]) -> type["BaseAgent"]:
        aid = agent_id or getattr(c, "agent_id", c.__name__)
        _AGENT_REGISTRY[aid] = c
        return c
    if cls is None:
        return _wrap
    return _wrap(cls)


def get_registered_agents() -> dict[str, type["BaseAgent"]]:
    """Return a shallow copy of the global agent registry.

    Keys are ``agent_id`` strings; values are agent classes (not instances).
    """
    return dict(_AGENT_REGISTRY)


def get_agent_class(agent_id: str) -> type["BaseAgent"] | None:
    """Look up a registered agent class by its ``agent_id``.

    Returns *None* if no agent is registered under that id.
    """
    return _AGENT_REGISTRY.get(agent_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Exception classes
# ═══════════════════════════════════════════════════════════════════════════════


class AgentValidationError(Exception):
    """Raised when an agent's output fails validation."""


class AgentError(Exception):
    """Raised when an agent encounters an unrecoverable error during ``run()``."""


# ═══════════════════════════════════════════════════════════════════════════════
# BaseAgent
# ═══════════════════════════════════════════════════════════════════════════════


class BaseAgent(ABC):
    """Common contract for all agents in the multi-agent pipeline.

    Subclasses must define ``agent_id``, ``agent_name``, and ``run()``.

    Use the ``@register_agent`` decorator to auto-register new agents::

        @register_agent
        class MyAgent(BaseAgent):
            agent_id = "my_agent"
            agent_name = "My Agent"
            def run(self, context): ...
    """

    agent_id: str
    agent_name: str

    def __init__(
        self,
        mock_data: dict[str, Any] | None = None,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        """Initialise the agent.

        Args:
            mock_data: Optional demo data dict. If *None* the agent should
                use ``get_fallback()`` when LLM is unavailable.
            llm_client: Optional LLM client for real generation.
        """
        self.mock_data = mock_data or {}
        self.llm_client = llm_client

    # ── Core contract ──────────────────────────────────────────────────

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent and return a partial result dict.

        The returned dict MUST contain an ``"agent_step"`` key with at least:
        ``{"agent_id": ..., "agent_name": ..., "status": ..., "summary": ...}``.

        All other keys are merged into the orchestrator's accumulated context.
        """
        ...

    # ── Validation ─────────────────────────────────────────────────────

    def validate_result(self, result: dict[str, Any]) -> None:
        """Validate the agent's output after ``run()``.

        Override in subclasses to check for required fields.  Raise
        ``AgentValidationError`` if validation fails.

        The base implementation is a no-op.
        """

    def validate_context(self, context: dict[str, Any]) -> None:
        """Validate the agent's input context before ``run()``.

        Override in subclasses to enforce structured input contracts
        using Pydantic models from ``app.schemas.agent_context``.
        Raise ``AgentValidationError`` if the context is missing required keys.

        The base implementation is a no-op — agents are NOT required
        to use typed contexts.
        """

    # ── Fallback ───────────────────────────────────────────────────────

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return safe default values when the agent cannot produce real output.

        Override in subclasses to provide domain-specific empty structures.
        The base implementation returns a minimal failed-step marker.

        Args:
            context: Optional context dict (may be used to populate defaults).

        Returns:
            A dict safe for merging into the orchestrator result.
            Fallback data is always marked with ``source: "rule_based_fallback"``
            and ``quality_status: "fallback"`` so the frontend can distinguish
            real generation results from safe defaults.
        """
        return {
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": f"Agent '{self.agent_id}' fell back to defaults.",
                "error_reason": "Agent failed to produce output, using rule-based fallback",
                "source": "rule_based_fallback",
                "quality_status": "fallback",
                "started_at": None,
                "finished_at": None,
            }
        }

    # ── Step metadata helper ───────────────────────────────────────────

    def agent_step(self) -> dict[str, Any]:
        """Extract this agent's step metadata from mock_data (legacy).

        Returns a default step if no matching entry is found.
        """
        for step in self.mock_data.get("agent_steps", []):
            if step.get("agent_id") == self.agent_id:
                return step

        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "status": "completed",
            "summary": "Agent completed.",
            "started_at": None,
            "finished_at": None,
        }
