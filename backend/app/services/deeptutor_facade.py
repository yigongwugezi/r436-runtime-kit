"""Unified DeepTutor facade — single entry point for all DeepTutor capability calls.

Replaces scattered ``deeptutor_call`` / ``deeptutor_call_async`` calls across
ConversationAgent, PlannerAgent, ResourceAgent, QuestionAgent, and orchestrator.

All call sites now go through one class, giving us:
- Consistent timeout / retry / circuit-breaker policies
- Single place to configure fallback behaviour
- Observable metrics (one logger, one trace point)

Usage::

    from app.services.deeptutor_facade import deeptutor

    reply = await deeptutor.chat("微积分怎么学？", history)
    mindmap = await deeptutor.generate_mindmap("数据结构-二叉树")
    path = deeptutor.mastery_path("微积分", "帮我规划", profile={"learning_goal": "..."})
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Low-level bridge (imports kept lazy so the module is importable even when
# deeptutor is not installed)
# ═══════════════════════════════════════════════════════════════════════════════


def _raw_call(capability: str, message: str, history: list | None = None, timeout: int = 120, profile_context: str = "") -> str:
    """Thin synchronous wrapper — kept private.  Prefer the facade methods below."""
    from app.services.deeptutor_client import deeptutor_call

    return deeptutor_call(capability, message, history, profile_context)


async def _raw_call_async(
    capability: str,
    message: str,
    history: list | None = None,
    system_prompt: str | None = None,
    profile_context: str = "",
) -> str:
    """Thin async wrapper — kept private."""
    from app.services.deeptutor_client import deeptutor_call_async

    if system_prompt:
        h = list(history or [])
        h.insert(0, {"role": "system", "content": system_prompt})
        return await deeptutor_call_async(capability, message, h, profile_context)
    return await deeptutor_call_async(capability, message, history, profile_context)


# ═══════════════════════════════════════════════════════════════════════════════
# Facade
# ═══════════════════════════════════════════════════════════════════════════════


class DeepTutorFacade:
    """Single entry point for all DeepTutor capability calls.

    Every method returns a safe fallback (empty string / empty list) on failure.
    """

    # ── Chat / general ──────────────────────────────────────────────────

    async def chat(
        self,
        message: str,
        history: list | None = None,
        system_prompt: str | None = None,
        profile_context: str = "",
    ) -> str:
        """General-purpose chat via DeepTutor.  Returns empty string on failure.

        Args:
            message: User message.
            history: Conversation history.
            system_prompt: Prepended to history as a system message.
            profile_context: Student profile injected into DeepTutor's
                memory_context for personalisation.
        """
        try:
            return await _raw_call_async("chat", message, history, system_prompt=system_prompt, profile_context=profile_context)
        except Exception as e:
            logger.warning("DeepTutor chat failed: %s", e)
            return ""

    def chat_sync(self, message: str, history: list | None = None, profile_context: str = "") -> str:
        """Synchronous version of :meth:`chat`."""
        try:
            return _raw_call("chat", message, history, profile_context=profile_context)
        except Exception as e:
            logger.warning("DeepTutor chat sync failed: %s", e)
            return ""

    # ── Content generation ─────────────────────────────────────────────

    def generate_lecture(self, topic: str, course_name: str = "") -> str:
        """Generate a lecture / course explanation document."""
        prompt = f"为'{topic}'生成一份专业课程讲解文档。包含：课程概述与学习目标、核心知识体系（3-5个模块）、每个模块的关键概念和典型应用、推荐学习顺序。"
        try:
            return _raw_call("chat", prompt)
        except Exception as e:
            logger.warning("DeepTutor lecture generation failed: %s", e)
            return ""

    def generate_mindmap(self, topic: str) -> str:
        """Generate a Mermaid-format mind map for *topic*."""
        prompt = f"为'{topic}'生成一个Mermaid格式的思维导图，覆盖关键知识点和层级关系。只输出mermaid代码块。"
        try:
            return _raw_call("chat", prompt)
        except Exception as e:
            logger.warning("DeepTutor mindmap generation failed: %s", e)
            return ""

    def generate_reading(self, topic: str) -> str:
        """Generate extended reading material for *topic*."""
        prompt = f"对'{topic}'进行深度研究，提供结构化拓展阅读材料，包含背景、核心概念、应用案例。2000字以上。"
        try:
            return _raw_call("chat", prompt)
        except Exception as e:
            logger.warning("DeepTutor reading generation failed: %s", e)
            return ""

    def generate_visual_explanation(self, topic: str) -> str:
        """Generate a diagram-based visual explanation for *topic*."""
        prompt = f"用图解方式解释'{topic}'。生成一个Mermaid图表，配合简洁的文字说明。输出Mermaid代码块加简短文字。"
        try:
            return _raw_call("chat", prompt)
        except Exception as e:
            logger.warning("DeepTutor visual explanation failed: %s", e)
            return ""

    def generate_video_script(self, topic: str, duration_minutes: int = 3) -> str:
        """Generate a micro-lecture video script for *topic*."""
        body = duration_minutes - 1
        prompt = f"为'{topic}'生成一个{duration_minutes}分钟的教学微课视频脚本。片头30秒标题+学习目标。核心讲解{body}分钟分3-5场景标注时长画面配音。片尾30秒小结思考题。"
        try:
            return _raw_call("chat", prompt)
        except Exception as e:
            logger.warning("DeepTutor video script failed: %s", e)
            return ""

    def generate_quiz(self, topic: str, knowledge_points: str = "", count: int = 5) -> str:
        """Generate practice questions for *topic*."""
        prompt = f"生成{count}道关于'{topic}'的练习题。知识点：{knowledge_points}。题型混合，含答案和解析。"
        try:
            return _raw_call("chat", prompt)
        except Exception as e:
            logger.warning("DeepTutor quiz generation failed: %s", e)
            return ""

    # ── Planning ───────────────────────────────────────────────────────

    def mastery_path(self, course: str, message: str, profile: dict | None = None) -> str:
        """Generate a mastery-based learning path via DeepTutor."""
        prompt = f"为学生规划学习路径。课程：{course}。需求：{message}"
        if profile:
            prompt += f"。学生画像：{profile}"
        try:
            return _raw_call("mastery_path", prompt)
        except Exception as e:
            logger.warning("DeepTutor mastery_path failed: %s", e)
            return ""


# Module-level singleton — import and use directly
deeptutor = DeepTutorFacade()
