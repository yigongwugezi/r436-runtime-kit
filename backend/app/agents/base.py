"""Common agent contract with validation, fallback, and error handling.

All stage agents inherit from BaseAgent.  The contract now supports:

- Optional ``mock_data`` for explicit local demos only.
- ``validate_result()`` — override to enforce required output fields.
- ``get_fallback()`` — safe defaults returned when the agent fails or times out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.services.llm_client import BaseLLMClient


class AgentValidationError(Exception):
    """Raised when an agent's output fails validation."""


class AgentError(Exception):
    """Raised when an agent encounters an unrecoverable error during ``run()``."""


class BaseAgent(ABC):
    """Common contract for all agents in the multi-agent pipeline.

    Subclasses must define ``agent_id``, ``agent_name``, and ``run()``.
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
