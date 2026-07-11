"""Shared DeepTutor client — proper async (no nest_asyncio)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _setup_config():
    from app.config import settings
    api_key = os.environ.get("LLM_API_KEY") or settings.deepseek_api_key
    if not api_key:
        return False
    base_url = os.environ.get("LLM_BASE_URL") or settings.deepseek_base_url
    model = os.environ.get("LLM_MODEL") or settings.llm_model
    try:
        from deeptutor.services.llm.config import LLMConfig, set_scoped_llm_config
        cfg = LLMConfig(model=model, api_key=api_key, base_url=base_url, effective_url=base_url,
                        binding="openai", provider_name="openai_compatible", provider_mode="cloud")
        set_scoped_llm_config(cfg)
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ.setdefault("OPENAI_TIMEOUT", "120")
        return True
    except Exception as e:
        logger.debug("DT config: %s", e)
        return False


async def deeptutor_call_async(
    capability: str,
    message: str,
    history: list | None = None,
    profile_context: str = "",
    persona_context: str = "",
) -> str:
    """Proper async DeepTutor call — no nest_asyncio, no asyncio.run.

    Args:
        capability: DeepTutor capability name ("chat", "mastery_path", etc.)
        message: User message or prompt.
        history: Conversation history in OpenAI format.
        profile_context: Student profile text injected into DeepTutor's
            memory_context so it knows the student's background.
        persona_context: Behavioural instructions injected into DeepTutor's
            persona_context — used to override the default tutor persona
            for profiling conversations.
    """
    if not _setup_config():
        return ""
    try:
        from deeptutor.runtime import ChatOrchestrator
        from deeptutor.core.context import UnifiedContext
        from deeptutor.core.stream import StreamEventType
        ctx = UnifiedContext(
            user_message=message,
            conversation_history=history or [],
            language="zh",
            memory_context=profile_context or "",
            persona_context=persona_context or "",
            enabled_tools=["reason","brainstorm","read_memory","write_memory","ask_user"] if capability == "chat" else [],
        )
        if capability and capability != "chat":
            ctx.active_capability = capability
        parts = []
        async for event in ChatOrchestrator().handle(ctx):
            if event.type == StreamEventType.CONTENT:
                parts.append(str(event.content or ""))
        return "".join(parts)
    except Exception as e:
        logger.warning("DeepTutor %s failed: %s", capability, e)
        return ""


# Synchronous wrappers for sync agent use
def deeptutor_call(
    capability: str,
    message: str,
    history: list | None = None,
    profile_context: str = "",
    persona_context: str = "",
) -> str:
    import asyncio, concurrent.futures
    async def _call(): return await deeptutor_call_async(capability, message, history, profile_context, persona_context)
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _call()).result(timeout=120)
    except RuntimeError:
        return asyncio.run(_call())


def generate_mindmap(topic: str) -> str:
    return deeptutor_call("chat", f"为'{topic}'生成一个Mermaid格式的思维导图，覆盖关键知识点和层级关系。只输出mermaid代码块。")


def generate_research(topic: str) -> str:
    return deeptutor_call("chat", f"对'{topic}'进行深度研究，提供结构化拓展阅读材料，包含背景、核心概念、应用案例。2000字以上。")


def generate_visual_explanation(topic: str) -> str:
    return deeptutor_call("chat", f"用图解方式解释'{topic}'。生成一个Mermaid图表，配合简洁的文字说明。输出Mermaid代码块加简短文字。")


def generate_video_script(topic: str, duration_minutes: int = 3) -> str:
    body = duration_minutes - 1
    return deeptutor_call("chat", f"为'{topic}'生成一个{duration_minutes}分钟的教学微课视频脚本。片头30秒标题+学习目标。核心讲解{body}分钟分3-5场景标注时长画面配音。片尾30秒小结思考题。")


def generate_quiz(topic: str, knowledge_points: str = "", count: int = 5) -> str:
    return deeptutor_call("chat", f"生成{count}道关于'{topic}'的练习题。知识点：{knowledge_points}。题型混合，含答案和解析。")
