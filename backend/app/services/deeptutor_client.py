"""Shared DeepTutor client — proper async (no nest_asyncio)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


async def _direct_llm_fallback(
    message: str,
    history: list | None,
    profile_context: str,
    persona_context: str,
) -> str:
    """Keep chat available when DeepTutor's runtime cannot reach its provider."""
    from app.config import settings
    from app.services.llm_client import MockLLMClient, get_llm_client

    client = get_llm_client(settings.llm_provider)
    if isinstance(client, MockLLMClient):
        return ""
    messages: list[dict[str, str]] = []
    if persona_context:
        messages.append({"role": "system", "content": persona_context})
    if profile_context:
        messages.append({"role": "system", "content": profile_context})
    messages.extend(
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
        for item in (history or [])[-12:]
        if isinstance(item, dict) and item.get("content")
    )
    messages.append({"role": "user", "content": message})
    started = time.monotonic()
    try:
        return str(await asyncio.to_thread(client.chat, messages) or "").strip()
    except Exception as exc:
        logger.warning(
            "Configured chat provider failed: provider=%s error=%s elapsed_ms=%d",
            settings.llm_provider, type(exc).__name__, (time.monotonic() - started) * 1000,
        )
        return ""


async def _chat_fallback(
    capability: str,
    fallback_to_configured_llm: bool,
    message: str,
    history: list | None,
    profile_context: str,
    persona_context: str,
) -> str:
    if capability != "chat" or not fallback_to_configured_llm:
        return ""
    return await _direct_llm_fallback(message, history, profile_context, persona_context)


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
    config_overrides: dict | None = None,
    fallback_to_configured_llm: bool = False,
) -> str:
    """Proper async DeepTutor call — no nest_asyncio, no asyncio.run.

    Args:
        capability: DeepTutor capability name ("chat", "visualize", etc.)
        message: User message or prompt.
        history: Conversation history in OpenAI format.
        profile_context: Student profile text injected into DeepTutor's
            memory_context so it knows the student's background.
        persona_context: Behavioural instructions injected into DeepTutor's
            persona_context — used to override the default tutor persona
            for profiling conversations.
        config_overrides: Per-request config overrides passed to the
            capability (e.g. {"render_mode": "mermaid"} for visualize).
        fallback_to_configured_llm: Allow normal chat to use the configured
            provider only after DeepTutor fails or returns no content.
    """
    if not _setup_config():
        return await _chat_fallback(
            capability, fallback_to_configured_llm, message, history, profile_context, persona_context
        )
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
            config_overrides=config_overrides or {},
        )
        if capability and capability != "chat":
            ctx.active_capability = capability
        parts = []
        async for event in ChatOrchestrator().handle(ctx):
            if event.type == StreamEventType.CONTENT:
                parts.append(str(event.content or ""))
        reply = "".join(parts).strip()
        if reply:
            return reply
        logger.warning("DeepTutor %s returned no content", capability)
    except Exception as e:
        logger.warning("DeepTutor %s failed: %s", capability, e)
    return await _chat_fallback(
        capability, fallback_to_configured_llm, message, history, profile_context, persona_context
    )


# Synchronous wrappers for sync agent use
def deeptutor_call(
    capability: str,
    message: str,
    history: list | None = None,
    profile_context: str = "",
    persona_context: str = "",
    config_overrides: dict | None = None,
    fallback_to_configured_llm: bool = False,
) -> str:
    import asyncio, concurrent.futures
    async def _call(): return await deeptutor_call_async(
        capability, message, history, profile_context, persona_context, config_overrides,
        fallback_to_configured_llm,
    )
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _call()).result(timeout=120)
    except RuntimeError:
        return asyncio.run(_call())


def generate_mindmap(topic: str) -> str:
    """Generate a Mermaid mind map — delegates to MindMapTool for consistent output."""
    from app.services.multimodal_provider import MindMapTool
    result = MindMapTool().run({"topic": topic})
    if isinstance(result, dict) and result.get("status") == "success":
        return str((result.get("result") or {}).get("mermaid") or "")
    return ""


def generate_research(topic: str) -> str:
    """Deep research via DeepTutor deep_research capability."""
    return deeptutor_call("deep_research", topic, config_overrides={"mode": "report", "depth": "standard"})


def generate_visual_explanation(topic: str) -> str:
    """Generate a visual diagram explanation via DeepTutor visualize capability."""
    return deeptutor_call("visualize", f"用图解方式解释「{topic}」，配合简洁的文字说明。", config_overrides={"render_mode": "mermaid"})


def generate_video_script(topic: str, duration_minutes: int = 3) -> str:
    """Generate a micro-lecture video script. (No dedicated DeepTutor capability — uses chat.)"""
    body = duration_minutes - 1
    return deeptutor_call("chat", f"为'{topic}'生成一个{duration_minutes}分钟的教学微课视频脚本。片头30秒标题+学习目标。核心讲解{body}分钟分3-5场景标注时长画面配音。片尾30秒小结思考题。")


def generate_quiz(topic: str, knowledge_points: str = "", count: int = 5) -> str:
    """Generate practice questions via DeepTutor deep_question capability."""
    prompt = topic + (f"（知识点：{knowledge_points}）" if knowledge_points else "")
    return deeptutor_call("deep_question", prompt, config_overrides={
        "mode": "custom",
        "topic": topic,
        "num_questions": count,
    })


def generate_solution(question_stem: str, correct_answer: str = "", question_type: str = "choice") -> str:
    """Generate a step-by-step solution for a question via DeepTutor deep_solve capability.

    Forces the model to show complete reasoning steps, not just the final answer.
    """
    prompt_parts = [f"请逐步解答以下题目，展示完整的推导过程：\n\n{question_stem}"]
    if correct_answer:
        prompt_parts.append(f"\n\n（已知正确答案是：{correct_answer}，请推导出这个答案的完整过程）")
    prompt = "".join(prompt_parts)
    return deeptutor_call("deep_solve", prompt)
