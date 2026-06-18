"""Agent orchestrator with per-agent error isolation and timeout handling.

Coordinates the stage-1 multi-agent learning workflow.  Each agent runs in
isolation — one failure does not crash the pipeline.  Results are aggregated
and returned with structured step metadata.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.agents import (
    DiagnosisAgent,
    KnowledgeAgent,
    PlannerAgent,
    ProfileAgent,
    ResourceAgent,
    ReviewAgent,
)
from app.config import settings
from app.services.llm_client import get_llm_client


# ── Per-agent output keys — used for fallback population ──────────────

AGENT_OUTPUT_KEYS: dict[str, list[str]] = {
    "profile_agent": ["profile"],
    "knowledge_agent": ["knowledge_context"],
    "diagnosis_agent": ["diagnosis"],
    "planner_agent": ["learning_path", "estimatedDays"],
    "resource_agent": ["resources"],
    "review_agent": ["review"],
}


class AgentOrchestrator:
    """Coordinates the multi-agent learning workflow with error resilience.

    Each agent is executed independently.  If an agent fails or times out
    the pipeline continues with the next agent, and the partial result is
    returned with ``overall_status: "partial"``.

    Usage::

        orchestrator = AgentOrchestrator()
        result = orchestrator.run(
            session_id="sess_001",
            course_id="ai_intro",
            user_message="我是大三学生...",
        )
        # result["overall_status"]  -> "completed" | "partial" | "failed"
        # result["agent_steps"]     -> list of per-agent step dicts
    """

    def __init__(self) -> None:
        self.agent_timeout = settings.agent_timeout
        self.llm_client = get_llm_client(settings.llm_provider)
        self._mock_data: dict[str, Any] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    def run(
        self,
        session_id: str,
        course_id: str,
        user_message: str,
        profile_facts: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute the full multi-agent pipeline.

        Args:
            session_id: Current session identifier.
            course_id: Target course identifier.
            user_message: The constructed prompt to send to agents.

        Returns:
            A dict with keys: session_id, course_id, profile, diagnosis,
            learning_path, resources, knowledge_context, review,
            agent_steps, overall_status, overall_error.
        """
        context: dict[str, Any] = {
            "session_id": session_id,
            "course_id": course_id,
            "user_message": user_message,
            "profile_facts": profile_facts or {},
        }

        result: dict[str, Any] = {
            "session_id": session_id,
            "course_id": course_id,
            "agent_steps": [],
        }

        any_failed = False
        overall_error_parts: list[str] = []

        for agent in self._build_agents():
            merged_context = {**context, **result}
            step = self._run_single_agent(agent, merged_context)
            result["agent_steps"].append(step)

            if step["status"] == "completed":
                # Merge agent outputs (everything except the step metadata)
                for key in AGENT_OUTPUT_KEYS.get(agent.agent_id, []):
                    if key in step:
                        result[key] = step[key]
            elif step["status"] in {"failed", "timeout"}:
                any_failed = True
                err = step.get("error", "unknown error")
                overall_error_parts.append(f"{agent.agent_id}: {err}")
                # Populate fallback keys so downstream agents have empty structures
                for key in AGENT_OUTPUT_KEYS.get(agent.agent_id, []):
                    if key not in result:
                        result.setdefault(key, [] if key in {"resources", "learning_path"} else {})

        # Determine overall status
        if not result["agent_steps"]:
            result["overall_status"] = "failed"
            result["overall_error"] = "No agents were executed."
        elif any_failed:
            result["overall_status"] = "partial"
            result["overall_error"] = "; ".join(overall_error_parts) if overall_error_parts else None
        else:
            result["overall_status"] = "completed"
            result["overall_error"] = None

        # Ensure all expected output keys exist
        for key_list in AGENT_OUTPUT_KEYS.values():
            for key in key_list:
                result.setdefault(key, [] if key in {"resources", "learning_path"} else {})

        return result

    # ── Agent construction ─────────────────────────────────────────────

    def _build_agents(self) -> list:
        """Build the agent pipeline.

        ProfileAgent and ResourceAgent receive the LLM client for real
        generation.  Others use mock data for now (gradually migrating).
        """
        mock_data = self._load_mock_data() if settings.enable_mock_fallback else {}
        return [
            ProfileAgent(mock_data=mock_data, llm_client=self.llm_client),
            KnowledgeAgent(mock_data=mock_data),
            DiagnosisAgent(mock_data=mock_data),
            PlannerAgent(mock_data=mock_data),
            ResourceAgent(mock_data=mock_data, llm_client=self.llm_client),
            ReviewAgent(mock_data=mock_data),
        ]

    # ── Single-agent execution ─────────────────────────────────────────

    def _run_single_agent(self, agent, context: dict[str, Any]) -> dict[str, Any]:
        """Run a single agent with timeout and error handling.

        Returns a step dict compatible with ``AgentStepResult``.
        """
        start = time.time()
        step: dict[str, Any] = {
            "agent_id": agent.agent_id,
            "agent_name": agent.agent_name,
            "status": "failed",
            "summary": "",
            "error": None,
            "duration_ms": 0.0,
            "started_at": start,
            "finished_at": 0.0,
        }

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(agent.run, context)
                try:
                    partial = future.result(timeout=self.agent_timeout)
                except FuturesTimeoutError:
                    step["status"] = "timeout"
                    step["error"] = (
                        f"Agent '{agent.agent_id}' timed out after {self.agent_timeout}s"
                    )
                    step["finished_at"] = time.time()
                    step["duration_ms"] = (step["finished_at"] - start) * 1000

                    # Try to get fallback data
                    try:
                        fallback = agent.get_fallback(context)
                        agent_step = fallback.pop("agent_step", {})
                        step.update(agent_step)
                        step.update(fallback)
                    except Exception:
                        pass

                    return step

            # Agent completed — extract step metadata and outputs
            agent_step = partial.pop("agent_step", {})
            step.update(agent_step)
            step["status"] = agent_step.get("status", "completed")
            step["summary"] = agent_step.get("summary", "Agent completed successfully.")

            # Validate result if the agent supports it
            try:
                agent.validate_result(partial)
            except Exception as exc:
                step["status"] = "failed"
                step["error"] = f"Validation error: {exc}"

            # Merge output keys into the step dict for upstream aggregation
            for key in AGENT_OUTPUT_KEYS.get(agent.agent_id, []):
                if key in partial:
                    step[key] = partial[key]

        except Exception as exc:
            step["status"] = "failed"
            step["error"] = f"{type(exc).__name__}: {exc}"
            step["summary"] = f"Agent failed with {type(exc).__name__}."

            # Try fallback
            try:
                fallback = agent.get_fallback(context)
                agent_step = fallback.pop("agent_step", {})
                step.update(agent_step)
                step.update(fallback)
            except Exception:
                pass

        step["finished_at"] = time.time()
        step["duration_ms"] = (step["finished_at"] - start) * 1000
        return step

    # ── Mock data loader ───────────────────────────────────────────────

    def _load_mock_data(self) -> dict[str, Any]:
        """Load mock data from the demo file (cached)."""
        if self._mock_data is not None:
            return self._mock_data

        mock_file = settings.project_root / "backend" / "app" / "mock" / "demo_result.json"
        try:
            with mock_file.open("r", encoding="utf-8") as file:
                self._mock_data = json.load(file).get("data", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._mock_data = {}
        return self._mock_data
