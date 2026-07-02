"""
Agent orchestrator with per-agent error isolation and timeout handling.
v3: ConversationAgent 提升为外层总控，Orchestrator 只负责依次执行子 Agent。
意图判断和最终回复由外层的 ConversationAgent 统一处理。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from app.agents import (
    DiagnosisAgent,
    GradingAgent,
    KnowledgeAgent,
    PlannerAgent,
    ProfileAgent,
    QuestionAgent,
    ResourceAgent,
    ReviewAgent,
)
from app.config import settings
from app.services.conversation_state import conversation_store
from app.services.learning_tracker import learning_tracker
from app.services.llm_client import get_llm_client


# ── Per-agent output keys — used for fallback population ──────────────

PLANNER_METADATA_KEYS = [
    "priority_basis",
    "risk_flags",
    "stage_rationales",
    "diagnosis_used",
    "needs_more_diagnosis",
    "recommended_resource_strategy",
]


AGENT_OUTPUT_KEYS: dict[str, list[str]] = {
    "conversation_agent": ["action", "intent", "reply"],
    "profile_agent": ["profile"],
    "knowledge_agent": ["knowledge_context"],
    "diagnosis_agent": ["diagnosis"],
    "planner_agent": ["learning_path", "estimatedDays", *PLANNER_METADATA_KEYS],
    "question_agent": ["questions", "question_set_id"],
    "resource_agent": ["resources"],
    "review_agent": ["review"],
    "grading_agent": ["grading_result"],
}


class AgentOrchestrator:
    """Coordinates the multi-agent learning workflow with error resilience.

    v3 流程：
    1. ProfileAgent — 生成/更新学习画像
    2. KnowledgeAgent — 检索课程知识
    3. DiagnosisAgent — 诊断薄弱点
    4. PlannerAgent — 规划学习路径
    5. ResourceAgent — 生成学习资源
    6. ReviewAgent — 审查质量

    ConversationAgent 已提升为外层总控，不在此管道中。
    意图判断和最终回复由外层的 ConversationAgent 统一处理。
    """

    def __init__(self) -> None:
        self.agent_timeout = settings.agent_timeout
        self.llm_client = get_llm_client(settings.llm_provider)
        self._mock_data: dict[str, Any] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    AGENT_STAGE_MAP: dict[str, tuple[str, int]] = {
        "profile_agent":      ("profiling", 15),
        "knowledge_agent":    ("knowledge", 30),
        "diagnosis_agent":    ("diagnosis", 45),
        "question_agent":     ("generating", 60),
        "planner_agent":      ("planning", 65),
        "resource_agent":     ("generating", 80),
        "review_agent":       ("reviewing", 90),
        "grading_agent":      ("reviewing", 95),
    }

    def run(
        self,
        session_id: str,
        course_id: str,
        user_message: str,
        profile_facts: dict[str, str] | None = None,
        progress_callback: Callable | None = None,
        agents_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute the multi-agent pipeline.

        Args:
            session_id: Current session identifier.
            course_id: Target course identifier.
            user_message: The user's raw message (not constructed prompt).
            profile_facts: Optional pre-extracted profile facts.
            progress_callback: Optional ``(stage_key, stage_label, progress_pct) -> None``.
            agents_filter: 指定只运行哪些 Agent（如 ["planner_agent", "resource_agent"]）。
                          为 None 时运行全部。为 [] 时只运行 ProfileAgent 基线。

        Returns:
            A dict with keys: session_id, course_id, reply, profile, diagnosis,
            learning_path, resources, knowledge_context, review,
            agent_steps, overall_status, overall_error.
        """
        AGENT_LABELS = {
            "profile_agent":      "正在生成画像",
            "knowledge_agent":    "正在检索知识",
            "diagnosis_agent":    "正在诊断分析",
            "question_agent":     "正在生成试题",
            "planner_agent":      "正在规划路径",
            "resource_agent":     "正在生成资源",
            "review_agent":       "正在检查质量",
            "grading_agent":      "正在批改作答",
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
            "agents_run": [],
            "skip_pipeline": False,
            "skip_reason": "",
            "pipeline_executed": False,
        }

        any_failed = False
        overall_error_parts: list[str] = []

        # ── 构建 Agent 列表，按 agents_filter 过滤 ──
        agents = self._build_agents(agents_filter=agents_filter)

        # ── 自适应诊断检测 ──
        if agents_filter and "diagnosis_agent" in agents_filter and "question_agent" in agents_filter:
            context["mode"] = "adaptive"
            state = conversation_store.get(session_id)
            last_result = state.last_result or {}
            context["previous_grades"] = last_result.get("grading_results", [])

        # ── 路径动态调整检测（M5）──
        if agents_filter and "planner_agent" in agents_filter and "diagnosis_agent" in agents_filter:
            context["mode"] = "adjust"
            state = conversation_store.get(session_id)
            last_result = state.last_result or {}
            existing_path = last_result.get("learning_path", []) or []
            if existing_path:
                context["existing_path"] = existing_path
                context["grading_results"] = last_result.get("grading_results", [])

        # ── 判断是否跳过后续 Agent ──
        skip_pipeline = False

        for index, agent in enumerate(agents):
            merged_context = {**context, **result}
            step = self._run_single_agent(agent, merged_context)
            result["agent_steps"].append(step)
            result["agents_run"].append(agent.agent_id)

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

            # ── Report progress ──
            if progress_callback:
                stage_info = self.AGENT_STAGE_MAP.get(agent.agent_id, ("", 0))
                stage_key = stage_info[0]
                pct = stage_info[1]
                label = AGENT_LABELS.get(agent.agent_id, agent.agent_name)
                if stage_key:
                    progress_callback(stage_key, label, pct)

        # ── 如果跳过流水线（目前仅 unsafe 场景），填充默认值 ──
        if result.get("agents_run") == ["conversation_agent"] and result.get("action") == "none":
            skip_pipeline = True
            result["skip_reason"] = "conversation_only"

        if skip_pipeline:
            result["skip_pipeline"] = True
            result["pipeline_executed"] = False
            skipped_source = "conversation_only" if result.get("skip_reason") == "conversation_only" else "pipeline_skipped"
            self._ensure_output_defaults(result, source=skipped_source)
            result["overall_status"] = "completed"
            result["overall_error"] = None
            result["source"] = skipped_source
            return result

        # ── 检测是否使用了 fallback ──
        fallback_used = any(
            step.get("source") == "rule_based_fallback"
            or step.get("quality_status") == "fallback"
            or step.get("status") in ("failed", "timeout")
            for step in result.get("agent_steps", [])
            if isinstance(step, dict)
        )

        # ── 确定总体状态 ──
        if not result["agent_steps"]:
            result["overall_status"] = "failed"
            result["overall_error"] = "No agents were executed."
            result["source"] = "system"
        elif any_failed:
            result["overall_status"] = "partial"
            result["overall_error"] = "; ".join(overall_error_parts) if overall_error_parts else None
            result["source"] = "partial_with_fallback"
            result["pipeline_executed"] = True
            result["quality_status"] = "fallback"
            result["reason"] = "部分智能体生成失败，已使用规则兜底数据"
        else:
            result["overall_status"] = "completed"
            result["overall_error"] = None
            result["source"] = "agent_pipeline"
            result["pipeline_executed"] = True

        result["fallback_used"] = fallback_used

        # ── 确保所有输出 key 存在 ──
        self._ensure_output_defaults(result, source=result.get("source", "agent_pipeline"))

        return result

    def _ensure_output_defaults(self, result: dict[str, Any], source: str) -> None:
        for key_list in AGENT_OUTPUT_KEYS.values():
            for key in key_list:
                if key == "knowledge_context":
                    current = result.get(key)
                    if not isinstance(current, dict):
                        current = {}
                    current.setdefault("source", source)
                    current.setdefault("course_id", result.get("course_id", ""))
                    result[key] = current
                else:
                    result.setdefault(key, [] if key in {"resources", "learning_path", "agent_steps"} else {})
        self._normalize_learning_path_source(result)
        self._ensure_planner_metadata(result)

    def _ensure_planner_metadata(self, result: dict[str, Any]) -> None:
        has_planner_output = "learning_path" in result or any(key in result for key in PLANNER_METADATA_KEYS)
        metadata = result.get("planner_metadata") if isinstance(result.get("planner_metadata"), dict) else {}
        if not has_planner_output:
            result["planner_metadata"] = metadata
            return

        metadata["priority_basis"] = list(result.get("priority_basis") or [])
        metadata["risk_flags"] = list(result.get("risk_flags") or [])
        estimated_days = result.get("estimatedDays")
        if estimated_days is not None:
            metadata["estimated_days"] = estimated_days
            metadata["estimatedDays"] = estimated_days
        for key in (
            "stage_rationales",
            "diagnosis_used",
            "needs_more_diagnosis",
            "recommended_resource_strategy",
        ):
            if key in result:
                metadata[key] = result[key]
        result["planner_metadata"] = metadata

    def _normalize_learning_path_source(self, result: dict[str, Any]) -> None:
        for stage in result.get("learning_path") or []:
            if not isinstance(stage, dict):
                continue
            if stage.get("source") in {"rule_fallback", "fallback_rule"}:
                stage.setdefault("generation_mode", "rule_fallback")
                stage["source"] = "agent_generated"

    def _session_analytics(self, session_id: str) -> dict[str, Any]:
        """Load session-scoped behavior evidence without failing the agent pipeline."""
        try:
            analytics = learning_tracker.summary(session_id)
        except Exception:
            return {}
        return analytics if isinstance(analytics, dict) else {}

    # ── Agent construction ─────────────────────────────────────────────

    def _build_agents(self, agents_filter: list[str] | None = None) -> list:
        """构建 Agent 执行管道。

        顺序：ProfileAgent → KnowledgeAgent → DiagnosisAgent → PlannerAgent → ResourceAgent → ReviewAgent
        ConversationAgent 已提升为外层总控，不在此管道中。

        agents_filter: 如果提供，只构建列表中指定的 Agent。None 表示全部。
                      注意：ProfileAgent 总是包含（作为基线），除非显式排除。
        """
        mock_data = self._load_mock_data() if settings.enable_mock_fallback else {}
        downstream_llm = self._downstream_llm_client()

        all_agents = [
            ProfileAgent(mock_data=mock_data, llm_client=self.llm_client),
            KnowledgeAgent(mock_data=mock_data),
            DiagnosisAgent(mock_data=mock_data, llm_client=downstream_llm),
            QuestionAgent(mock_data=mock_data, llm_client=downstream_llm),
            PlannerAgent(mock_data=mock_data, llm_client=downstream_llm),
            ResourceAgent(mock_data=mock_data, llm_client=downstream_llm),
            ReviewAgent(mock_data=mock_data),
            GradingAgent(mock_data=mock_data, llm_client=downstream_llm),
        ]

        if agents_filter is None:
            return all_agents

        filter_set = set(agents_filter)
        # ProfileAgent 总是包含在主 Agent 调用的默认中，除非 filter 明确为空列表
        if not filter_set:
            return []

        return [a for a in all_agents if a.agent_id in filter_set]

    def _downstream_llm_client(self):
        return self.llm_client

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
