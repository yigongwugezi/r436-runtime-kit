"""Shared DeepTutor client — proper async (no nest_asyncio)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)
_DIRECT_CHAT_TIMEOUT_SECONDS = 8

# Module-level storage for the last RESULT event metadata captured during a
# deeptutor_call / deeptutor_call_async invocation.  Callers that need
# structured output (e.g. quiz questions) can access it immediately after
# the call returns via :func:`get_last_result_metadata`.
_last_result_metadata: dict[str, Any] = {}


def get_last_result_metadata() -> dict[str, Any]:
    """Return the last captured RESULT event metadata dict, or an empty dict."""
    return _last_result_metadata


async def _direct_llm_fallback(
    message: str,
    history: list | None,
    profile_context: str,
    persona_context: str,
) -> str:
    """Keep chat available when DeepTutor's runtime cannot reach its provider."""
    from app.config import settings
    from app.services.llm_client import MockLLMClient, get_llm_client
    from app.utils.errors import AIConfigMissingError

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
        timeout = min(_DIRECT_CHAT_TIMEOUT_SECONDS, max(1, int(settings.llm_request_timeout)))
        return str(await asyncio.to_thread(client.chat, messages, timeout=timeout, retry_count=1) or "").strip()
    except AIConfigMissingError:
        raise  # 未配置 key → 引导用户，不能吞成空回复
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
    """Configure DeepTutor's scoped LLM config from the current user's credentials.

    Uses ``set_scoped_llm_config`` only — the API key is NEVER written into
    ``os.environ`` (process-global env would leak one user's key into every
    other user's requests).
    """
    import os as _os

    from app.services.user_ai_config import get_llm_credentials

    creds = get_llm_credentials()
    if creds["provider"] == "mock" or not creds["api_key"]:
        return False
    try:
        from deeptutor.services.llm.config import LLMConfig, set_scoped_llm_config
        cfg = LLMConfig(model=creds["model"], api_key=creds["api_key"], base_url=creds["base_url"],
                        effective_url=creds["base_url"],
                        binding="openai", provider_name="openai_compatible", provider_mode="cloud")
        set_scoped_llm_config(cfg)
        _os.environ.setdefault("OPENAI_TIMEOUT", "120")  # technical setting, no secret
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

        # Per-capability default tools.  Chat gets the full composer surface;
        # research pipelines get the evidence-producing tools their block loop
        # actually allows (RESEARCH_BLOCK_TOOL_ALLOWLIST).
        _capability_tools: dict[str, list[str]] = {
            "deep_research": ["web_search"],
        }
        enabled_tools = _capability_tools.get(
            capability,
            ["reason", "brainstorm", "ask_user"] if capability == "chat" else [],
        )

        ctx = UnifiedContext(
            user_message=message,
            conversation_history=history or [],
            language="zh",
            memory_context=profile_context or "",
            persona_context=persona_context or "",
            enabled_tools=enabled_tools,
            config_overrides=config_overrides or {},
        )
        if capability and capability != "chat":
            ctx.active_capability = capability
        parts = []
        result_response = ""
        _last_result_metadata.clear()
        async for event in ChatOrchestrator().handle(ctx):
            if event.type == StreamEventType.CONTENT:
                parts.append(str(event.content or ""))
            elif event.type == StreamEventType.RESULT:
                meta = event.metadata or {}
                if isinstance(meta, dict):
                    _last_result_metadata.update(meta)
                    result_response = str(meta.get("response") or "")
        reply = "".join(parts).strip()
        # Prefer the structured RESULT response when it carries more content
        # than the live-streamed CONTENT events (typical for capabilities like
        # deep_question / deep_research where the final output is in RESULT).
        if result_response and len(result_response) > len(reply):
            reply = result_response
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
    timeout: int = 120,
) -> str:
    import asyncio, concurrent.futures
    from app.services.user_ai_config import copy_context_wrap
    async def _call(): return await deeptutor_call_async(
        capability, message, history, profile_context, persona_context, config_overrides,
        fallback_to_configured_llm,
    )
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # copy_context_wrap: 工作线程不继承 ContextVar，需带入当前用户凭据上下文
            return pool.submit(copy_context_wrap(asyncio.run), _call()).result(timeout=timeout)
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
    """Deep research via DeepTutor deep_research capability.

    The research pipeline is a two-stage flow: the first call returns an
    outline for user confirmation; the second call with ``confirmed_outline``
    actually executes the research blocks and generates the report.  This
    wrapper automates both stages so callers get the final report directly.
    """
    config = {"mode": "report", "depth": "standard"}

    # Stage 1: get outline (only runs Phase 1 Rephrase + Phase 2 Decompose)
    deeptutor_call("deep_research", topic, config_overrides=config, timeout=120)
    meta = get_last_result_metadata()
    # The pipeline returns sub-topics under either "sub_topics" or "outline"
    outline = (meta.get("sub_topics") or meta.get("outline") or []) if isinstance(meta, dict) else []
    logger.info("Research stage 1 complete: outline=%d items, meta_keys=%s",
                len(outline) if isinstance(outline, list) else 0,
                list(meta.keys()) if isinstance(meta, dict) else "not_dict")

    if not outline:
        # No outline — pipeline may have failed; return whatever response we got
        return str(meta.get("response") or "")

    # Stage 2: run full research with confirmed outline
    confirmed_outline = [
        {"title": str(it.get("title", "")), "overview": str(it.get("overview", ""))}
        for it in outline
        if isinstance(it, dict) and it.get("title")
    ]
    if not confirmed_outline:
        return str(meta.get("response") or "")

    return deeptutor_call("deep_research", topic, config_overrides={
        **config,
        "confirmed_outline": confirmed_outline,
    }, timeout=300)


def generate_visual_explanation(topic: str) -> str:
    """Generate a visual diagram explanation via DeepTutor visualize capability."""
    return deeptutor_call("visualize", f"用图解方式解释「{topic}」，配合简洁的文字说明。", config_overrides={"render_mode": "mermaid"})


def generate_video_script(topic: str, duration_minutes: int = 3) -> str:
    """Generate a micro-lecture video script. (No dedicated DeepTutor capability — uses chat.)"""
    body = duration_minutes - 1
    return deeptutor_call("chat", f"为'{topic}'生成一个{duration_minutes}分钟的教学微课视频脚本。片头30秒标题+学习目标。核心讲解{body}分钟分3-5场景标注时长画面配音。片尾30秒小结思考题。")


def generate_quiz(topic: str, knowledge_points: str = "", count: int = 5):
    """Generate practice questions via DeepTutor deep_question capability.

    Returns a dict with ``content`` (markdown string) and ``questions``
    (list of structured question dicts ready for frontend QuizAnswerer).
    """
    prompt = topic + (f"（知识点：{knowledge_points}）" if knowledge_points else "")
    content = deeptutor_call("deep_question", prompt, config_overrides={
        "mode": "custom",
        "topic": topic,
        "num_questions": count,
    }, timeout=300)

    # Parse structured questions from the pipeline's RESULT metadata
    meta = get_last_result_metadata()
    summary = meta.get("summary", {}) if isinstance(meta, dict) else {}
    results = summary.get("results", []) if isinstance(summary, dict) else []

    questions: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        qa = r.get("qa_pair", {}) if isinstance(r.get("qa_pair"), dict) else {}
        stem = str(qa.get("question") or "").strip()
        if not stem:
            continue
        q_type = str(qa.get("question_type") or "choice").strip()
        raw_options = qa.get("options")
        option_list: list[str] | None = None
        if isinstance(raw_options, dict) and raw_options:
            option_list = [str(raw_options.get(k, "")) for k in ("A", "B", "C", "D") if k in raw_options]
        questions.append({
            "id": str(qa.get("question_id") or f"q{len(questions) + 1}"),
            "type": "choice" if q_type == "choice" else q_type,
            "stem": stem,
            "options": option_list,
            "answer": str(qa.get("correct_answer") or ""),
            "explanation": str(qa.get("explanation") or ""),
            "knowledgePoint": str(qa.get("concentration") or topic),
            "difficulty": str(qa.get("difficulty") or "medium"),
        })

    return {"content": content, "questions": questions}


def generate_solution(question_stem: str, correct_answer: str = "", question_type: str = "choice") -> str:
    """Generate a step-by-step solution for a question via DeepTutor deep_solve capability.

    Forces the model to show complete reasoning steps, not just the final answer.
    """
    prompt_parts = [f"请逐步解答以下题目，展示完整的推导过程：\n\n{question_stem}"]
    if correct_answer:
        prompt_parts.append(f"\n\n（已知正确答案是：{correct_answer}，请推导出这个答案的完整过程）")
    prompt = "".join(prompt_parts)
    return deeptutor_call("deep_solve", prompt)
