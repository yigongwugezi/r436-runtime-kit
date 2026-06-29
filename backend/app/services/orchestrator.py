"""Agent orchestrator with per-agent error isolation and timeout handling.

Coordinates the stage-1 multi-agent learning workflow.  Each agent runs in
isolation — one failure does not crash the pipeline.  Results are aggregated
and returned with structured step metadata.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from typing import Any, Callable

from app.agents import (
    DiagnosisAgent,
    KnowledgeAgent,
    PlannerAgent,
    ProfileAgent,
    ResourceAgent,
    ReviewAgent,
)
from app.config import settings
from app.services.learning_tracker import learning_tracker
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

# ── Per-agent LLM progress ranges for chunk-level interpolation ──────
# (pct_start, pct_end, max_tokens_or_None)
AGENT_LLM_RANGES: dict[str, tuple[int, int, int | None]] = {
    "profile_agent": (10, 25, None),
    "planner_agent": (40, 55, 1600),
    "resource_agent": (55, 75, 2200),
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

    # ── Stage-to-progress mapping ─────────────────────────────────
    AGENT_STAGE_MAP: dict[str, tuple[str, int]] = {
        "profile_agent":   ("profiling", 25),
        "knowledge_agent": ("knowledge", 30),
        "diagnosis_agent": ("diagnosis", 40),
        "planner_agent":   ("planning",  55),
        "resource_agent":  ("generating", 75),
        "review_agent":    ("reviewing",  85),
    }

    def run(
        self,
        session_id: str,
        course_id: str,
        user_message: str,
        profile_facts: dict[str, str] | None = None,
        progress_callback: Callable | None = None,
    ) -> dict[str, Any]:
        """Execute the full multi-agent pipeline.

        Args:
            session_id: Current session identifier.
            course_id: Target course identifier.
            user_message: The constructed prompt to send to agents.
            progress_callback: Optional ``(stage_key, stage_label, progress_pct) -> None``.

        Returns:
            A dict with keys: session_id, course_id, profile, diagnosis,
            learning_path, resources, knowledge_context, review,
            agent_steps, overall_status, overall_error.
        """
        AGENT_LABELS = {
            "profile_agent": "正在生成画像",
            "knowledge_agent": "正在检索知识",
            "diagnosis_agent": "正在诊断分析",
            "planner_agent": "正在规划路径",
            "resource_agent": "正在生成资源",
            "review_agent": "正在检查质量",
        }
        context: dict[str, Any] = {
            "session_id": session_id,
            "course_id": course_id,
            "user_message": user_message,
            "profile_facts": profile_facts or {},
            "analytics": self._session_analytics(session_id),
        }

        result: dict[str, Any] = {
            "session_id": session_id,
            "course_id": course_id,
            "agent_steps": [],
        }

        any_failed = False
        overall_error_parts: list[str] = []

        # ── Wave-based execution ────────────────────────────────────
        # Wave 1: ProfileAgent (LLM call — must complete first)
        # Wave 2: KnowledgeAgent + DiagnosisAgent (no LLM, parallel)
        # Wave 3: PlannerAgent (LLM call)
        # Wave 4: ResourceAgent (LLM + RAG)
        # Wave 5: ReviewAgent (no LLM)
        WAVES: list[list[str]] = [
            ["profile_agent"],
            ["knowledge_agent", "diagnosis_agent"],
            ["planner_agent"],
            ["resource_agent"],
            ["review_agent"],
        ]
        agent_map = {a.agent_id: a for a in self._build_agents()}

        def _merge_step(agent_id: str, step: dict[str, Any]) -> None:
            """Merge a completed agent step into the result dict."""
            nonlocal any_failed
            result["agent_steps"].append(step)

            if step["status"] == "completed":
                for key in AGENT_OUTPUT_KEYS.get(agent_id, []):
                    if key in step:
                        result[key] = step[key]
            elif step["status"] in {"failed", "timeout"}:
                any_failed = True
                err = step.get("error", "unknown error")
                overall_error_parts.append(f"{agent_id}: {err}")
                for key in AGENT_OUTPUT_KEYS.get(agent_id, []):
                    if key not in result:
                        result.setdefault(
                            key,
                            [] if key in {"resources", "learning_path"} else {},
                        )

            # Report progress after each agent completes
            if progress_callback:
                stage_key = self.AGENT_STAGE_MAP.get(agent_id, ("", 0))[0]
                pct = self.AGENT_STAGE_MAP.get(agent_id, ("", 0))[1]
                label = AGENT_LABELS.get(agent_id, "Unknown")
                if stage_key:
                    progress_callback(stage_key, label, pct)

        for wave in WAVES:
            agents_in_wave = [
                agent_map[aid] for aid in wave if aid in agent_map
            ]
            if not agents_in_wave:
                continue

            if len(agents_in_wave) == 1:
                agent = agents_in_wave[0]
                merged_context = {**context, **result}
                step = self._run_single_agent(
                    agent, merged_context, progress_callback=progress_callback
                )
                _merge_step(agent.agent_id, step)
            else:
                # Parallel execution for independent agents
                merged_context = {**context, **result}
                with ThreadPoolExecutor(max_workers=len(agents_in_wave)) as executor:
                    futures = {
                        executor.submit(
                            self._run_single_agent,
                            agent,
                            merged_context,
                            progress_callback,
                        ): agent
                        for agent in agents_in_wave
                    }
                    for future in as_completed(futures):
                        agent = futures[future]
                        step = future.result()
                        _merge_step(agent.agent_id, step)

        # Determine overall status
        if not result["agent_steps"]:
            result["overall_status"] = "failed"
            result["overall_error"] = "No agents were executed."
            result["source"] = "system"
        elif any_failed:
            result["overall_status"] = "partial"
            result["overall_error"] = "; ".join(overall_error_parts) if overall_error_parts else None
            result["source"] = "partial_with_fallback"
            result["quality_status"] = "fallback"
            result["reason"] = "部分智能体生成失败，已使用规则兜底数据"
        else:
            result["overall_status"] = "completed"
            result["overall_error"] = None
            result["source"] = "agent_pipeline"

        # Ensure all expected output keys exist
        for key_list in AGENT_OUTPUT_KEYS.values():
            for key in key_list:
                result.setdefault(key, [] if key in {"resources", "learning_path"} else {})

        return result

    def _session_analytics(self, session_id: str) -> dict[str, Any]:
        """Load session-scoped behavior evidence without failing the agent pipeline."""
        try:
            analytics = learning_tracker.summary(session_id)
        except Exception:
            return {}
        return analytics if isinstance(analytics, dict) else {}

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
            PlannerAgent(mock_data=mock_data, llm_client=self.llm_client),
            ResourceAgent(mock_data=mock_data, llm_client=self.llm_client),
            ReviewAgent(mock_data=mock_data),
        ]

    # ── Single-agent execution ─────────────────────────────────────────

    def _run_single_agent(
        self,
        agent,
        context: dict[str, Any],
        progress_callback: Callable | None = None,
    ) -> dict[str, Any]:
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

        # ── Wire chunk callback for agents that use LLM ────────────────
        chunk_registered = False
        if (
            hasattr(self.llm_client, "set_chunk_callback")
            and agent.agent_id in AGENT_LLM_RANGES
            and progress_callback
        ):
            llm_range = AGENT_LLM_RANGES[agent.agent_id]
            pct_start, pct_end, max_tokens = llm_range
            token_count = [0]  # mutable counter for closure

            def on_llm_chunk(_token_text: str) -> None:
                token_count[0] += 1
                if max_tokens and max_tokens > 0:
                    sub_pct = pct_start + (token_count[0] / max_tokens) * (
                        pct_end - pct_start
                    )
                    sub_pct = min(sub_pct, pct_end)
                else:
                    # No max_tokens known — creep forward slowly
                    sub_pct = pct_start + ((token_count[0] % 50) / 50) * (
                        pct_end - pct_start
                    ) * 0.1
                    sub_pct = min(pct_start + 0.5 * (pct_end - pct_start), sub_pct)

                stage_key = self.AGENT_STAGE_MAP.get(agent.agent_id, ("", 0))[0]
                label_map = {
                    "profile_agent": "正在生成画像",
                    "knowledge_agent": "正在检索知识",
                    "diagnosis_agent": "正在诊断分析",
                    "planner_agent": "正在规划路径",
                    "resource_agent": "正在生成资源",
                    "review_agent": "正在检查质量",
                }
                label = label_map.get(agent.agent_id, agent.agent_name)
                detail = f"已生成 {token_count[0]} 个字符..."
                progress_callback(stage_key, label, sub_pct, detail=detail)

            self.llm_client.set_chunk_callback(on_llm_chunk)
            chunk_registered = True

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
                        import logging
                        logging.getLogger("app.services.orchestrator").warning(
                            "Failed to merge fallback for agent %s",
                            step.get("agent_id", "unknown"),
                        )

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
                import logging
                logging.getLogger("app.services.orchestrator").warning(
                    "Failed to merge fallback in outer handler for agent %s",
                    step.get("agent_id", "unknown"),
                )

        finally:
            if chunk_registered and hasattr(self.llm_client, "set_chunk_callback"):
                self.llm_client.set_chunk_callback(None)

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
