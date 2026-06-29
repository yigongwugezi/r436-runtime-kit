"""
Agent orchestrator with per-agent error isolation and timeout handling.
v2: 增加 ConversationAgent 做对话理解，LLM 优先，规则兜底。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from app.agents import (
    ConversationAgent,
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
    "conversation_agent": ["reply", "action", "intent"],
    "knowledge_agent": ["knowledge_context"],
    "diagnosis_agent": ["diagnosis"],
    "planner_agent": ["learning_path", "estimatedDays"],
    "resource_agent": ["resources"],
    "review_agent": ["review"],
}


class AgentOrchestrator:
    """Coordinates the multi-agent learning workflow with error resilience.

    v2 流程：
    1. ProfileAgent — 生成/更新学习画像
    2. ConversationAgent — LLM 理解用户意图，生成自然回复 + 决策
    3. 根据 ConversationAgent 的 action 决定是否继续后续 Agent
    4. KnowledgeAgent → DiagnosisAgent → PlannerAgent → ResourceAgent → ReviewAgent

    如果 ConversationAgent 的 action 是 "none" 或 "unsafe"，跳过后续 Agent。
    """

    def __init__(self) -> None:
        self.agent_timeout = settings.agent_timeout
        self.llm_client = get_llm_client(settings.llm_provider)
        self._mock_data: dict[str, Any] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    AGENT_STAGE_MAP: dict[str, tuple[str, int]] = {
        "profile_agent":      ("profiling", 15),
        "conversation_agent": ("understanding", 25),
        "knowledge_agent":    ("knowledge", 35),
        "diagnosis_agent":    ("diagnosis", 50),
        "planner_agent":      ("planning", 65),
        "resource_agent":     ("generating", 80),
        "review_agent":       ("reviewing", 90),
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
            user_message: The user's raw message (not constructed prompt).
            profile_facts: Optional pre-extracted profile facts.
            progress_callback: Optional ``(stage_key, stage_label, progress_pct) -> None``.

        Returns:
            A dict with keys: session_id, course_id, reply, profile, diagnosis,
            learning_path, resources, knowledge_context, review,
            agent_steps, overall_status, overall_error.
        """
        AGENT_LABELS = {
            "profile_agent":      "正在生成画像",
            "conversation_agent": "正在理解意图",
            "knowledge_agent":    "正在检索知识",
            "diagnosis_agent":    "正在诊断分析",
            "planner_agent":      "正在规划路径",
            "resource_agent":     "正在生成资源",
            "review_agent":       "正在检查质量",
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

        # ── 构建 Agent 列表 ──
        agents = self._build_agents()

        # ── 判断是否跳过后续 Agent ──
        skip_pipeline = False

        for agent in agents:
            merged_context = {**context, **result}
            step = self._run_single_agent(agent, merged_context)
            result["agent_steps"].append(step)

            if step["status"] == "completed":
                for key in AGENT_OUTPUT_KEYS.get(agent.agent_id, []):
                    if key in step:
                        result[key] = step[key]
            elif step["status"] in {"failed", "timeout"}:
                any_failed = True
                err = step.get("error", "unknown error")
                overall_error_parts.append(f"{agent.agent_id}: {err}")
                for key in AGENT_OUTPUT_KEYS.get(agent.agent_id, []):
                    if key not in result:
                        result.setdefault(key, [] if key in {"resources", "learning_path"} else {})

            # ── ConversationAgent 决策：是否需要继续 ──
            if agent.agent_id == "conversation_agent":
                action = result.get("action", "none")
                if action in ("none", "unsafe"):
                    skip_pipeline = True
                    break  # 纯对话/不安全，跳过后续所有 Agent

            # ── Report progress ──
            if progress_callback:
                stage_info = self.AGENT_STAGE_MAP.get(agent.agent_id, ("", 0))
                stage_key = stage_info[0]
                pct = stage_info[1]
                label = AGENT_LABELS.get(agent.agent_id, agent.agent_name)
                if stage_key:
                    progress_callback(stage_key, label, pct)

        # ── 如果跳过流水线，填充默认值 ──
        if skip_pipeline:
            for key_list in AGENT_OUTPUT_KEYS.values():
                for key in key_list:
                    result.setdefault(key, [] if key in {"resources", "learning_path", "agent_steps"} else {})
            result["overall_status"] = "completed"
            result["overall_error"] = None
            result["source"] = "conversation_only"
            return result

        # ── 确定总体状态 ──
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

        # ── 确保所有输出 key 存在 ──
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

        顺序：
        1. ProfileAgent — 画像（如果已有画像会跳过）
        2. ConversationAgent — LLM 理解意图（新增）
        3-7. 原流水线
        """
        mock_data = self._load_mock_data() if settings.enable_mock_fallback else {}
        return [
            ProfileAgent(mock_data=mock_data, llm_client=self.llm_client),
            ConversationAgent(mock_data=mock_data, llm_client=self.llm_client),
            KnowledgeAgent(mock_data=mock_data),
            DiagnosisAgent(mock_data=mock_data, llm_client=self.llm_client),
            PlannerAgent(mock_data=mock_data, llm_client=self.llm_client),
            ResourceAgent(mock_data=mock_data, llm_client=self.llm_client),
            ReviewAgent(mock_data=mock_data),
        ]

    # ── Single-agent execution ─────────────────────────────────────────

    def _run_single_agent(self, agent, context: dict[str, Any]) -> dict[str, Any]:
        """Run a single agent with timeout and error handling."""
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

                    try:
                        fallback = agent.get_fallback(context)
                        agent_step = fallback.pop("agent_step", {})
                        step.update(agent_step)
                        step.update(fallback)
                    except Exception:
                        import logging
                        logging.getLogger("app.services.orchestrator").warning(
                            "Failed to merge fallback for agent %s", step.get("agent_id", "unknown")
                        )

                    return step

            # Agent completed — extract step metadata and outputs
            agent_step = partial.pop("agent_step", {})
            step.update(agent_step)
            step["status"] = agent_step.get("status", "completed")
            step["summary"] = agent_step.get("summary", "Agent completed successfully.")

            try:
                agent.validate_result(partial)
            except Exception as exc:
                step["status"] = "failed"
                step["error"] = f"Validation error: {exc}"

            for key in AGENT_OUTPUT_KEYS.get(agent.agent_id, []):
                if key in partial:
                    step[key] = partial[key]

        except Exception as exc:
            step["status"] = "failed"
            step["error"] = f"{type(exc).__name__}: {exc}"
            step["summary"] = f"Agent failed with {type(exc).__name__}."

            try:
                fallback = agent.get_fallback(context)
                agent_step = fallback.pop("agent_step", {})
                step.update(agent_step)
                step.update(fallback)
            except Exception:
                import logging
                logging.getLogger("app.services.orchestrator").warning(
                    "Failed to merge fallback in outer handler for agent %s", step.get("agent_id", "unknown")
                )

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