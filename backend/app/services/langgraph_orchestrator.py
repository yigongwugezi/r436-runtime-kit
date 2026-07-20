"""Unified LangGraph orchestrator — intent routing + pipeline + feedback loop (async).

Refactored (Phase 2):
  - AgentFactory replaces _make_agents() → lazy, shared LLM client
  - IntentRouter replaces 3 scattered intent→agent maps → single source of truth
  - Single ConversationAgent per request via factory cache
  - DeepTutorFacade replaces scattered deeptutor_call calls
  - Generalized RetryPolicy replaces hardcoded _after_review
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.base import get_agent_class
from app.services.agent_factory import AgentFactory
from app.services.intent_router import (
    get_node_route, get_agent_ids, should_run_agents,
    chat_only_intents,
)
from app.services.deeptutor_facade import deeptutor

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


# ═══════════════════════════════════════════════════════════════════════════════
# Fact extraction after chat — closes the loop between conversation and profile
# ═══════════════════════════════════════════════════════════════════════════════

async def _extract_facts_after_chat(
    session_id: str,
    user_msg: str,
    assistant_reply: str,
    existing_facts: dict,
) -> None:
    """After a chat turn, extract facts with probe-aware extraction.

    Unlike a simple fact-extractor, this understands that:
    - A diagnostic quiz answer reveals knowledge_base (if correct) OR weak_points (if wrong)
    - A concept explanation reveals depth of understanding, not just surface facts
    - A preference choice made in context is more reliable than a self-report
    - Evidence must be tagged: [探测], [学生自述], or [行为观察]
    """
    if not session_id or not user_msg or not assistant_reply:
        return

    # ── Detect probe type from assistant message ──
    _probe_type = ""
    _diagnostic_markers = ["考你一下", "你觉得对吗", "下面哪个", "正确的是", "以下哪个", "判断", "测测", "摸底"]
    _concept_markers = ["你能解释", "说说看", "用自己的话", "什么是", "的区别是"]
    _preference_markers = ["文字解释还是", "画个图", "哪种方式", "你喜欢"]
    _scenario_markers = ["如果", "你会怎么", "遇到", "试试看"]
    _goal_markers = ["最想做到", "学完", "能自己", "目标"]
    _time_markers = ["整块还是", "碎片", "周末也", "最少能"]

    if any(m in assistant_reply for m in _diagnostic_markers):
        _probe_type = "diagnostic_quiz"
    elif any(m in assistant_reply for m in _concept_markers):
        _probe_type = "concept_explanation"
    elif any(m in assistant_reply for m in _preference_markers):
        _probe_type = "preference_choice"
    elif any(m in assistant_reply for m in _scenario_markers):
        _probe_type = "scenario_test"
    elif any(m in assistant_reply for m in _goal_markers):
        _probe_type = "goal_probe"
    elif any(m in assistant_reply for m in _time_markers):
        _probe_type = "time_reality_check"

    _probe_hints = {
        "diagnostic_quiz": (
            "上一轮AI出了一道诊断题。根据学生回答的对错和解释质量，提取画像：\n"
            "- 学生答对且解释清楚 → 提取到 knowledge_base，例如'[探测]能正确判断XXX'\n"
            "- 学生答错或回避 → 提取到 weak_points，例如'[探测]对YYY理解有误'\n"
            "- 不要只看学生说了什么——要结合AI的分析来判断对错"
        ),
        "concept_explanation": (
            "上一轮AI让学生解释了一个概念。根据解释的准确性和深度：\n"
            "- 解释清晰准确 → 提取到 knowledge_base，附带掌握程度\n"
            "- 解释模糊或错误 → 提取到 weak_points，标注概念混淆的具体点"
        ),
        "preference_choice": (
            "上一轮AI给了学生一个学习方式的自然选择（文字vs图解等）。\n"
            "从学生的选择中提取 preference，evidence标记为[行为观察]"
        ),
        "scenario_test": (
            "上一轮用场景题探测了学生能力。从回答中提取 knowledge_base 或 weak_points。"
        ),
        "goal_probe": (
            "上一轮深入探测了学习目标的真实动机和具体程度。\n"
            "提取 learning_goal 为有深度的描述，区分'通过考试'和'想拿90分'。"
        ),
        "time_reality_check": (
            "上一轮确认了时间安排的真实性（整块vs碎片，理想vs实际）。\n"
            "提取 time_budget 为区分了工作日/周末/下限的具体描述。"
        ),
    }

    probe_context = ""
    if _probe_type:
        probe_context = (
            "\n## 本轮探测类型：" + _probe_type + "\n"
            + _probe_hints.get(_probe_type, "")
            + "\n- 提取的值必须带上 evidence 来源标记：[探测]、[学生自述]、或[行为观察]\n"
            + "- 值要具体到可操作的程度，避免笼统描述\n"
        )

    # Build a focused fact-extraction prompt with the conversation context
    label_map = {
        "background": "专业/年级/身份背景",
        "target_course": "想学的课程/方向",
        "knowledge_base": "已有基础（具体学过什么、到什么程度）",
        "weak_points": "薄弱点/卡点（具体哪个概念或题型）",
        "learning_goal": "学习目标（考试/项目/入门，具体到什么程度）",
        "time_budget": "时间安排（每天多久、连续还是碎片）",
        "preference": "学习偏好（文字/视频/图解/做题）",
    }
    known_lines = []
    unknown_lines = []
    for key, label in label_map.items():
        val = str(existing_facts.get(key, "")).strip()
        if val and val not in ("未提及", "待补充", "未知", "", "无"):
            known_lines.append(f"  {label}：{val}")
        else:
            unknown_lines.append(f"  {label}：未知")

    known_block = "\n".join(known_lines) if known_lines else "（暂无）"
    unknown_block = "\n".join(unknown_lines) if unknown_lines else "（全部已知）"

    fact_prompt = (
        "你是一个多相分析提取器。从对话中提取学生的深层信息，每个维度可以有多项独立的分析结果。\n"
        "注意：结合AI和学生双方的发言综合分析。不仅记录显式信息，还要从回答中推断额外信息。\n\n"
        "提取维度及每维的分析要求：\n"
        "规则：\n"
        "- 每个维度可以有多个 topics——学生的回答往往包含多层信息，要全部提取出来\n"
        "- 有交叉推断的单独列一个 topic，confidence 降到 0.3-0.5\n"
        "- 提取时尽量具体——'软件工程大二' 优于 '大学生'，'链式法则卡住了' 优于 '数学薄弱'\n"
        "- 薄弱点附加 evidence 来源标记：[探测]（诊断验证）、[学生自述]、[行为观察]\n"
        "- 如果某维度在对话中无新信息，整个维度不输出\n"
        + probe_context + "\n"
        f"## 当前已知\n{known_block}\n\n"
        f"## 尚未了解\n{unknown_block}\n\n"
        f"## 对话\n学生：{user_msg[:500]}\nAI：{assistant_reply[:600]}\n\n"
        "输出JSON，rich_updates 每个维度的值是一个对象，可包含 summary（字符串）、topics（数组）、gaps_found（数组）：\n"
        '{"updates": {"background": "[学生自述]软件工程大二"}, "rich_updates": {\n'
        '  "knowledge_base": {\n'
        '    "summary": "有C语言基础和二进制概念",\n'
        '    "topics": [\n'
        '      {"topic": "C语言", "level": "intermediate", "detail": "变量、函数、指针", "confidence": 0.9, "evidence": "学生自述"},\n'
        '      {"topic": "二进制", "level": "beginner", "detail": "知道原码反码补码", "confidence": 0.8, "evidence": "学生自述"},\n'
        '      {"topic": "逻辑门", "level": "beginner", "detail": "知道与或非门", "confidence": 0.7, "evidence": "学生自述"}\n'
        '    ],\n'
        '    "gaps_found": ["数字电路设计", "CPU数据通路", "指令集体系结构"]\n'
        '  },\n'
        '  "weak_points": {\n'
        '    "summary": "对网络核心概念有误解",\n'
        '    "topics": [\n'
        '      {"topic": "电路交换", "level": "none", "detail": "认为数据传输需要建立专用通路", "confidence": 0.8, "evidence": "[探测]"},\n'
        '      {"topic": "分组交换", "level": "none", "detail": "不了解分组交换的基本原理", "confidence": 0.6, "evidence": "[推断]"}\n'
        '    ]\n'
        '  },\n'
        '  "time_budget": {\n'
        '    "summary": "工作日每天3小时，周末休息",\n'
        '    "topics": [\n'
        '      {"topic": "每日时长", "level": "", "detail": "工作日每天3小时", "confidence": 0.9, "evidence": "学生自述"},\n'
        '      {"topic": "周末安排", "level": "", "detail": "周末休息不学习", "confidence": 0.9, "evidence": "学生自述"},\n'
        '      {"topic": "总时间", "level": "", "detail": "每周约15小时", "confidence": 0.9, "evidence": "学生自述"}\n'
        '    ]\n'
        '  }\n'
        "}}")

    try:
        from app.services.deeptutor_facade import deeptutor
        raw = await deeptutor.chat(fact_prompt, [], profile_context="", persona_context="")
        if not raw or len(raw) < 20:
            return

        import json as _json
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s >= 0 and e > s:
            updates = _json.loads(raw[s:e]).get("updates", {})
        else:
            return

        if not isinstance(updates, dict) or not updates:
            return

        from app.services.conversation_state import conversation_store
        state = conversation_store.get(session_id)
        if state is None:
            return
        for key, value in updates.items():
            if key in label_map and value and str(value).strip():
                val = str(value).strip()
                if val and val not in ("未提及", "待补充", "未知", "", "无") and len(val) > 1:
                    conversation_store._set_fact(state, key, val, source_text=user_msg)

        # ── 处理 rich_updates（结构化 topic 级数据）──
        try:
            rich = _json.loads(raw[s:e]).get("rich_updates", {})
        except Exception:
            rich = {}
        if isinstance(rich, dict):
            for dim, data in rich.items():
                if dim not in label_map:
                    continue
                summary = str(data.get("summary", "")).strip() if isinstance(data, dict) else ""
                if summary:
                    conversation_store._set_fact(state, dim, summary, source_text=user_msg)
                topics = data.get("topics", []) if isinstance(data, dict) else []
                if isinstance(topics, list):
                    for t in topics:
                        if isinstance(t, dict) and t.get("topic"):
                            conversation_store.set_rich_fact_topic(
                                state, dim, str(t["topic"]),
                                level=str(t.get("level", "")),
                                detail=str(t.get("detail", "")),
                                confidence=float(t.get("confidence", 0.5)),
                                evidence=str(t.get("evidence", "")),
                                source_text=user_msg,
                                verified_by=str(t.get("verified_by", "")),
                            )
                # ── 处理 gaps_found（知识差距）──
                gaps = data.get("gaps_found", []) if isinstance(data, dict) else []
                if isinstance(gaps, list) and gaps:
                    rich_dim = state.rich_facts.setdefault(dim, {"topics": [], "gaps_found": []})
                    for g in gaps:
                        g_text = str(g).strip()
                        if g_text and g_text not in rich_dim.get("gaps_found", []):
                            rich_dim.setdefault("gaps_found", []).append(g_text)
    except Exception:
        pass  # Fact extraction is best-effort, never blocks the reply


# ═══════════════════════════════════════════════════════════════════════════════
# Profile context helpers — shared between conversation node and ConversationAgent
# ═══════════════════════════════════════════════════════════════════════════════

_LABEL_MAP = {
    "background": "专业/年级",
    "target_course": "想学的课程",
    "knowledge_base": "已有基础",
    "weak_points": "薄弱点",
    "learning_goal": "学习目标",
    "time_budget": "时间安排",
    "preference": "学习偏好",
}


def _chat_fallback_reply(message: str, messages: list[dict[str, Any]] | None = None) -> tuple[str, dict[str, bool]]:
    """Return a safe, current-turn fallback when chat providers are unavailable."""
    current_message = str(message or "").strip()
    user_messages = [m for m in messages or [] if isinstance(m, dict) and m.get("role") == "user"]
    is_new_conversation = len(user_messages) <= 1
    current_message_is_empty = not current_message
    compact = re.sub(r"\s+", "", current_message).lower()
    current_message_is_greeting = compact in {"你好", "您好", "嗨", "哈喽", "hello", "hi"}
    meta = {
        "is_new_conversation": is_new_conversation,
        "current_message_is_greeting": current_message_is_greeting,
        "current_message_is_empty": current_message_is_empty,
    }
    if current_message_is_empty:
        return "我没有收到具体内容，可以再说明一下吗？", meta
    if current_message_is_greeting:
        return "你好！我是EduAgent，有什么可以帮你的吗？", meta

    background = re.search(r"(?:我是一名|我是|本人是)\s*([^，。,.!?！？]{2,30})", current_message)
    if background and any(token in background.group(1) for token in ("大一", "大二", "大三", "大四", "研究生", "本科", "专业", "工程", "计算机", "学生")):
        return f"了解，你目前是{background.group(1).strip()}。我会结合这个学习阶段调整后续建议。", meta
    if "喜欢" in current_message and any(token in current_message for token in ("视频", "图解", "动画", "文字", "练习", "实操")):
        return "收到，你偏好通过视频学习；后续讲解我会优先采用这种方式。", meta
    if any(token in current_message for token in ("这次", "当前", "本次")) and any(token in current_message for token in ("简单", "简要", "概览", "了解一下")):
        return "明白，这次我会先用简要的方式说明，不把这个临时偏好写成长期设置。", meta
    if "身份信息" in current_message and any(token in current_message for token in ("复述", "刚才", "告诉")):
        for item in reversed(user_messages[:-1]):
            previous = str(item.get("content") or "")
            match = re.search(r"(?:我是一名|我是|本人是)\s*([^，。,.!?！？]{2,30})", previous)
            if match:
                return f"你刚才提到自己是{match.group(1).strip()}。", meta
    learning = re.search(r"(?:我想(?:学习|学|了解)|我想要(?:学习|学|了解))\s*(?:一下)?\s*([^，。,.!?！？]{2,30})", current_message)
    if learning:
        topic = learning.group(1).strip(" 的")
        if topic:
            return f"可以。你想先从{topic}的基础概念开始，还是针对其中的具体主题继续了解？", meta
    return "我没有完全理解你的意思，可以再具体说明一下吗？", meta


def _is_usable_chat_reply(reply: str, message: str) -> bool:
    """Reject provider default templates when they do not answer this turn."""
    text = str(reply or "").strip()
    current = str(message or "").strip()
    compact = re.sub(r"\s+", "", current).lower()
    is_greeting = compact in {"你好", "您好", "嗨", "哈喽", "hello", "hi"}
    is_explicit_fact = bool(re.search(r"(?:我是一名|我是|本人是)\s*[^，。,.!?！？]{2,30}", current))
    is_preference = "喜欢" in current and any(token in current for token in ("视频", "图解", "动画", "文字", "练习", "实操"))
    is_temporary = any(token in current for token in ("这次", "当前", "本次")) and any(token in current for token in ("简单", "简要", "概览", "了解一下"))
    is_recap = "身份信息" in current and any(token in current for token in ("复述", "刚才", "告诉"))
    if not text:
        return False
    if "你好！我是EduAgent" in text and not is_greeting:
        return False
    clarification_template = text.startswith(("我没有完全理解", "我不太理解", "可以再具体说明"))
    if clarification_template and current:
        return False
    return True


def _profile_query_reply(message: str, profile_v2: dict[str, Any] | None, profile_facts: dict[str, Any]) -> str:
    """Answer a small, explicit self-profile query without exposing profile internals."""
    text = str(message or "")
    asks_preference = any(token in text for token in ("学习偏好", "喜欢通过什么方式", "喜欢怎么学习", "偏好"))
    asks_background = any(token in text for token in ("年级", "身份", "记住"))
    if not (asks_preference or asks_background):
        return ""

    profile = profile_v2 if isinstance(profile_v2, dict) else {}
    if not profile:
        return ""
    records = profile.get("fact_records") if isinstance(profile.get("fact_records"), dict) else {}
    context = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}

    def value_for(keys: tuple[str, ...], fallback_key: str) -> str:
        candidates = []
        for key in keys:
            record = records.get(key)
            if isinstance(record, dict) and record.get("is_disabled_for_personalization"):
                return ""
            if not isinstance(record, dict) or record.get("status", "active") != "active":
                continue
            if record.get("scope", "global") not in {"global", "subject", "course", "path", "session"}:
                continue
            value = record.get("value")
            if value not in (None, "", [], {}):
                candidates.append((0 if record.get("fact_type") == "explicit" else 1, value))
        if candidates:
            value = sorted(candidates, key=lambda item: item[0])[0][1]
        else:
            value = context.get(keys[0]) or profile_facts.get(fallback_key)
        if isinstance(value, list):
            return "、".join(str(item) for item in value if str(item).strip())
        return str(value or "").strip()

    background = value_for(("background",), "background") if asks_background else ""
    preference = value_for(("resource_preferences", "content_preferences", "preference"), "preference") if asks_preference else ""
    parts = []
    if background:
        parts.append(f"你目前是{background}")
    if preference:
        parts.append(f"你偏好通过{preference}学习")
    if parts:
        return "；".join(parts) + "。"
    return "我目前还没有记录到相关的学习画像信息。"


async def _chat_provider_reply(message: str, messages: list[dict[str, Any]], profile_context: str, persona_context: str) -> tuple[str, str]:
    """Use DeepTutor first, then retry the configured provider only for a rejected template."""
    reply = await deeptutor.chat(message, messages, profile_context=profile_context, persona_context=persona_context)
    if _is_usable_chat_reply(reply, message):
        logger.info("Chat provider deeptutor returned a usable reply")
        return reply, "deeptutor"
    try:
        from app.services.deeptutor_client import _direct_llm_fallback
        direct_reply = await _direct_llm_fallback(message, messages, profile_context, persona_context)
        if _is_usable_chat_reply(direct_reply, message):
            logger.info("Chat provider deepseek returned a usable reply")
            return direct_reply, "deepseek"
    except Exception:
        logger.warning("Chat provider deepseek failed safely")
    return "", ""


def _is_likely_chat(msg: str, facts: dict) -> bool:
    """Quick check: is this message almost certainly casual chat?
    Avoids the full ConversationAgent overhead for the common case."""
    compact = re.sub(r"\s+", "", msg)
    # Explicit generation triggers → need full classification
    gen_triggers = ["生成", "出题", "规划", "批改", "诊断", "路径", "资源", "导图",
                    "系统学", "专攻", "按章节", "每日学", "每日计划", "薄弱点", "强化",
                    "调整", "修改", "改一下", "加快", "放慢", "重新",
                    "计划", "制定", "安排",
                    "开始", "想学", "我要学"]
    if any(t in compact for t in gen_triggers):
        return False
    # Everything else is probably chat
    return True


def _build_profile_context(facts: dict[str, str]) -> str:
    """Build a natural-language student-profile summary for DeepTutor's memory_context."""
    parts: list[str] = []
    for key, label in _LABEL_MAP.items():
        value = str(facts.get(key, "")).strip()
        if value and value not in ("未提及", "待补充", "未知", "", "无"):
            parts.append(f"{label}：{value}")
    if not parts:
        return ""
    return (
        "【学生画像——仅供你了解学生，不要在回复中逐条复述这些信息，"
        "而是在对话中自然地融入你对学生的了解】\n" + "\n".join(parts)
    )


def _summarize_known_facts(facts: dict[str, str]) -> str:
    """One-line summary of what we know about the student."""
    parts = []
    for key, label in _LABEL_MAP.items():
        val = str(facts.get(key, "")).strip()
        if val and val not in ("未提及", "待补充", "未知", "", "无"):
            parts.append(f"{label}={val}")
    return "；".join(parts) if parts else "暂无"


def _all_dims_deep(facts: dict[str, str]) -> bool:
    """Check if all 7 core dimensions have deep (non-shallow) answers.

    A dimension is shallow only if the entire value is essentially just a
    shallow keyword — e.g. "零基础" alone is shallow, but "零基础未学过数字电路
    和汇编但逻辑直觉不错" is not.
    """
    from app.services.conversation_state import _SHALLOW_PATTERNS

    required = set(_LABEL_MAP.keys())
    for dim in required:
        val = str(facts.get(dim, "")).strip()
        if not val or val in ("未提及", "待补充", "未知", "", "无"):
            return False
        # Only flag as shallow if the value is JUST the keyword (plus minor padding)
        for p in _SHALLOW_PATTERNS:
            if val == p or (len(val) <= len(p) + 4 and p in val):
                return False
    return True


def _build_chat_persona(facts: dict[str, str], textbook_title: str = "") -> str:
    """Build persona instructions that override DeepTutor's default tutor persona.

    The persona guides DeepTutor through profile-building with per-dimension
    probing strategies — each dimension has its own indirect method, not just
    direct questioning.  Deep understanding of each dimension is the
    prerequisite for true personalisation.

    When *textbook_title* is non-empty, the student already has a defined
    subject scope: the persona skips ``target_course`` probing and adds a
    leading instruction to focus the conversation on that textbook.
    """
    from app.services.conversation_state import _SHALLOW_PATTERNS

    filled = {k for k, v in facts.items() if v and str(v).strip() and str(v).strip() not in ("未提及", "待补充", "未知", "", "无")}
    total = len(_LABEL_MAP)

    # Detect shallow vs deep per dimension
    # "微积分" is 3 chars but perfectly valid — don't flag short answers as shallow.
    # Only flag as shallow if the value contains a known shallow/generic phrase.
    shallow_keys: set[str] = set()
    deep_keys: set[str] = set()
    for k in filled:
        val = str(facts.get(k, "")).strip()
        # Only flag as shallow if the value is essentially just the keyword
        is_shallow = False
        for p in _SHALLOW_PATTERNS:
            if val == p or (len(val) <= len(p) + 4 and p in val):
                is_shallow = True
                break
        if is_shallow:
            shallow_keys.add(k)
        else:
            deep_keys.add(k)
    missing_keys = set(_LABEL_MAP) - filled

    deep_pct = len(deep_keys) / max(1, total)

    # ═══════════════════════════════════════════════════════════════════
    # Per-dimension probing instructions — generated dynamically based on
    # what's missing vs shallow vs deep for THIS student.
    # ═══════════════════════════════════════════════════════════════════

    def _probe_for(key: str) -> str:
        """Return a dimension-specific probing instruction."""
        label = _LABEL_MAP.get(key, key)
        course = str(facts.get("target_course", "")).strip()

        strategies: dict[str, str] = {
            "background": (
                f"[{label}] 不要只问专业名。学生说了专业后追问方向——\n"
                "例如: 软件工程的话偏前端还是AI？大二的话专业课上了哪些？\n"
                "从学生用的术语也能推断背景——说'计组课'就是CS，说'高数课'就是理工科。\n"
                "追问具体方向，不是泛泛的专业名。"
            ),
            "target_course": (
                f"[{label}] 不要只问想学什么。追问为什么想学和想学到什么程度。\n"
                "'为什么'能暴露真实动机(考试被迫/项目需要/纯兴趣)。\n"
                "'什么程度'能区分'了解概念就行' vs '想能独立做题'。\n"
                "这两个问题的答案决定了整个学习方案的深度和节奏。"
            ),
            "knowledge_base": (
                f"[{label}] *** 核心探测维度——绝对不要问'你基础怎么样' ***\n"
                "用以下方法组合探测，根据课程类型选择最合适的方法:\n"
                "1. 出诊断题——抛一道概念判断/选择题: 如果我说XXX，你觉得对吗？\n"
                "2. 让解释概念——你能用自己的话说说YYY是什么吗？从解释的准确性判断真懂假懂\n"
                "3. 追问技术点——学生说'学过Python' -> 追问列表推导式、装饰器、上下文管理器\n"
                "4. 场景测试——如果让你写一个XXX功能，你会怎么设计？\n"
                "探测后在心里打分: 完全不会/知道概念/能看懂/能独立做/能教别人\n"
                "记住: 出题只是方法之一，不同课程用不同方法——编程课看代码，数学课看推导，语言课看表达"
            ),
            "weak_points": (
                f"[{label}] *** 核心探测维度——绝对不要问'你哪里薄弱' ***\n"
                "薄弱点很难靠直接问得到，因为学生自己往往不知道哪里薄弱。用以下方法:\n"
                "1. 从 knowledge_base 探测中暴露——学生答错/解释不清的地方 = 薄弱点\n"
                "2. 问经历——之前学这门课，哪种题/哪个章节最头疼？\n"
                "3. 问反应——如果考试出了一道XXX类型的题，你第一反应是什么？\n"
                "4. 交叉验证——用探测结果和学生自我描述比对，矛盾的才是真薄弱点\n"
                + (f"5. 如果{course or '目标课程'}有明确章节，按章节问——极限、导数、积分，哪个最没把握？\n" if course else "") +
                "注意: 薄弱点要具体到题型或概念，不是'数学比较弱'这种笼统描述"
            ),
            "learning_goal": (
                f"[{label}] 不要只问'为了考试还是做项目'。用以下方式深入:\n"
                "1. 问未来——学完这门课你最想能做到什么？(具体成果 > 抽象目标)\n"
                "2. 问紧迫感——这个目标有时间要求吗？(区分'最好能学会'和'下个月就要考')\n"
                "3. 观察提问模式——学生问'这个会考吗'(应试型)还是'这个怎么用到XX上'(应用型)\n"
                "4. 问放弃条件——如果时间不够，哪些内容你觉得可以跳过？(暴露真正的优先级)"
            ),
            "time_budget": (
                f"[{label}] 直接问但确认真实性，不要满足于一个数字:\n"
                "1. 每天2小时是整块的还是碎片化的？(碎片化时间学习效率完全不同)\n"
                "2. 周末也一样吗？还是有其他安排？(区分工作日和周末)\n"
                "3. 如果某天特别忙，你最少能挤出多少时间？(测试真实下限)\n"
                "这些追问决定了学习方案是激进还是保守"
            ),
            "preference": (
                f"[{label}] 行为探测比直接问更准——不要问'你喜欢什么方式':\n"
                "1. 对话中自然抛出选择——我用文字解释还是画个图？\n"
                "2. 观察反应——说'画个图吧'就是视觉型；说'直接推公式'就是抽象型\n"
                "3. 问历史——你以前学东西，是喜欢先看原理还是先看例子？\n"
                "4. 如果学生用了 LecturePage，观察他点了哪些内容类型，但不要在对话里说"
            ),
        }
        return strategies.get(key, f"【{label}】请深入了解学生的{label}，追问具体细节。")

    # ═══════════════════════════════════════════════════════════════════
    # Build probing priorities: shallow first (need deepening), then missing
    # ═══════════════════════════════════════════════════════════════════
    priority_order = ["target_course", "background", "knowledge_base", "weak_points", "learning_goal", "time_budget", "preference"]

    # v1.2: 教材已确定 → 无需追问 target_course
    if textbook_title:
        priority_order = [d for d in priority_order if d != "target_course"]

    # Dimensions that need work this turn
    need_probing = list(shallow_keys)  # shallow → need deepening
    for k in priority_order:
        if k in missing_keys and k not in need_probing:
            need_probing.append(k)

    # Focus on 2-3 dimensions at most per turn
    focus_dims = need_probing[:3]
    probing_sections = "\n\n".join(_probe_for(k) for k in focus_dims)
    other_shallow = [k for k in shallow_keys if k not in focus_dims]
    other_missing = [k for k in missing_keys if k not in focus_dims]

    # ═══════════════════════════════════════════════════════════════════
    # Stage-specific guidance
    # ═══════════════════════════════════════════════════════════════════

    if deep_pct < 0.4:
        stage_guidance = (
            "你正在逐步了解这个学生——目前还处于早期阶段，离生成方案还远。\n"
            "每轮聚焦 1 个维度深入了解，不要急着跳到生成。\n\n"
            "*** 所有维度通用规则：学生的自述不可信，必须间接验证 ***\n"
            "- background：不要只问专业名。追问具体方向、上过哪些课，从术语推断真实背景。\n"
            "- target_course：不要只问想学什么。追问为什么、想到什么程度、有没有具体时间节点。\n"
            "- knowledge_base：不要问'你基础怎么样'。出诊断题、让解释概念、抛判断题——从对错和解释质量打分。\n"
            "- weak_points：不要问'你哪里薄弱'。从诊断题答错/解释不清的地方暴露，交叉验证。\n"
            "- learning_goal：不要只问'考试还是做项目'。追问'学完最想做到什么'、'如果时间不够哪部分可跳过'。\n"
            "- time_budget：不要只问一个数字。追问是整块还是碎片、周末能不能学、最少能挤出多少。\n"
            "- preference：不要问'喜欢什么方式'。在对话中自然抛选择（'文字解释还是画图？'），从行为中观察。\n\n"
            "任何维度只靠学生随口一说就算过了的，视为未探测。"
        )
    elif deep_pct < 0.7:
        stage_guidance = (
            "你对学生有了基本了解，但离真正的个性化规划还差得远。\n"
            "现在重点是：把模糊的回答变具体，把直接询问变为间接探测。\n"
            "每个维度的值必须具体、可验证、有证据来源（诊断结果/行为观察/交叉验证），\n"
            "不能是学生随口说的笼统描述。\n"
            "如果 knowledge_base 还没做过诊断题，这一轮必须补——\n"
            "薄弱点只能从诊断中暴露，问是问不出来的。"
        )
    elif deep_pct < 1.0 or shallow_keys:
        stage_guidance = (
            "你对学生的了解已经比较全面了。现在要做的是：\n"
            "1. 回顾已了解的信息，用你自己的话总结并向学生确认\n"
            "2. 对仍然模糊的维度做最后一轮追问\n"
            "3. 确认后，用自然语气总结画像。系统会自动弹出模式选择器。\n\n"
            "*** 确认前逐维度自查（任何一项不满足就继续探测）***\n"
            "- background：是否具体到专业+年级+方向？\n"
            "- target_course：是否有为什么学+想学到什么程度？\n"
            "- knowledge_base：是否经过了诊断验证（出题/解释概念/判断）而非仅靠自述？\n"
            "- weak_points：是否具体到题型或概念（不是'数学弱'这种笼统话）？\n"
            "- learning_goal：是否有具体可衡量的目标（不是'想学好'这种）？\n"
            "- time_budget：是否有每天多久+整块还是碎片+是否有例外情况？\n"
            "- preference：是否通过行为观察验证（不是学生随口说的'喜欢看书'）？"
        )
    else:
        stage_guidance = (
            "你对学生的了解已经非常深入了。\n"
            "按顶部 🛑 指令操作——总结画像后直接输出模式选择标签，不要绕弯子。"
        )

    # ═══════════════════════════════════════════════════════════════════
    # Assemble the final persona
    # ═══════════════════════════════════════════════════════════════════
    parts = []

    # ── v1.2: 教材已确定 — 直接引导 LLM 围绕教材对话 ──
    if textbook_title:
        parts.append(
            f"📖 学生已关联教材《{textbook_title}》。该教材的结构、章节和教学范围已确定，"
            f"你不需要问 target_course（想学什么科目/课程）——直接围绕这本教材展开对话。"
            f"在了解学生背景、基础、目标等维度时，自然地引用教材中的章节或主题。"
        )
        parts.append("")

    # Hard stop: if all dimensions are deep enough, force proposal NOW.
    # This goes FIRST so the model can't miss it while in "teaching mode".
    if not shallow_keys and not missing_keys:
        parts.append(
            "🛑 所有 7 个维度都已探测完毕。\n"
            "用自然语气简单总结画像，告诉学生画像已经完整。\n"
            "不要生成方案、不要出题、不要开始教学。总结完就停。\n"
            "系统会自动弹出模式选择器。"
        )
        parts.append("")

    parts.append(stage_guidance)
    parts.append("")
    parts.append("━━━ 本轮聚焦探测的维度 ━━━")
    parts.append(probing_sections)
    if other_shallow:
        parts.append(f"\n⚠️ 以下维度回答太模糊，后续需要追问：{'、'.join(_LABEL_MAP.get(k, k) for k in other_shallow)}")
    if other_missing:
        parts.append(f"尚未了解：{'、'.join(_LABEL_MAP.get(k, k) for k in other_missing)}")
    parts.append("\n记住：深入了解每个维度是生成个性化方案的前提。不要急着跳到生成。")
    parts.append(
        "\n⚠️ 一次只深入一个维度，问一个问题。绝对禁止用 | 分隔多个问题——"
        "那是填表式提问，不是自然对话。学生回答后再自然过渡到下一个维度。"
    )
    parts.append(
        "\n🚫 绝对禁止在聊天中直接生成任何规划类内容——包括但不限于：学习方案、"
        "时间表、周计划、日计划、章节安排、里程碑、学习路线图。你只负责了解和探测学生。"
        "当你认为画像已经足够深入时，总结画像后系统会自动弹出模式选择器。"
        "学生点击按钮后后端规划器会自动接管，你不要越俎代庖。"
        "即使学生催促你'开始吧''直接给我方案'，在画像不完整时也必须继续探测。"
    )

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Retry policy — generalized from the old hardcoded _after_review
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RetryPolicy:
    """Per-agent retry policy for quality-feedback loops."""
    max_retries: int = 2
    retry_on_check_ids: tuple[str, ...] = ()
    retry_node: str = ""          # which LangGraph node to loop back to
    notify_upstream: tuple[str, ...] = ()  # nodes to notify on retry (future use)


# Default policies — easily extensible
RETRY_POLICIES: dict[str, RetryPolicy] = {
    "resource": RetryPolicy(
        max_retries=2,
        retry_on_check_ids=(
            "resource_content_quality", "resource_coverage",
            "resource_type_match", "semantic_quality",
        ),
        retry_node="resource",
        notify_upstream=("planner",),
    ),
}


def _resolve_retry_route(state: dict) -> str:
    """Generalized post-review routing.

    Iterates over RETRY_POLICIES and loops back to the first matching
    agent node that hasn't exceeded its retry budget.
    """
    review = state.get("review", {})
    quality_status = review.get("quality_status", "passed")
    if quality_status not in ("blocked", "failed", "warning"):
        return "reply"

    checks = review.get("checks", [])
    for agent_node, policy in RETRY_POLICIES.items():
        has_issues = any(
            c.get("check_id") in policy.retry_on_check_ids
            and c.get("status") in ("blocked", "warning")
            for c in checks
        )
        if has_issues:
            retries = state.get("_retry_count", 0)
            if retries < policy.max_retries:
                state["_retry_count"] = retries + 1
                logger.info(
                    "Review flagged %s issues (retry %d/%d), looping back to %s",
                    agent_node, state["_retry_count"], policy.max_retries, policy.retry_node,
                )
                return policy.retry_node

    return "reply"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent execution helpers
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_agent(agent_id: str, state: dict, factory: AgentFactory) -> dict:
    """Run a single agent by its short key (e.g. "planner", "resource")."""
    full_agent_id = f"{agent_id}_agent"  # short key → agent_id convention
    agent = factory.get(full_agent_id)
    if agent is None:
        logger.error("Unknown agent: %s", agent_id)
        state.setdefault("agent_steps", []).append({"node": agent_id, "error": "unknown_agent"})
        return state
    ctx = dict(state)
    ctx["_retry_count"] = state.get("_retry_count", 0)
    result = await asyncio.to_thread(agent.run, ctx)
    for k, v in result.items():
        if k != "agent_step":
            state[k] = v
    state.setdefault("agent_steps", []).append(result.get("agent_step", {}))
    return state


async def _run_conversation_agent(context: dict[str, Any], factory: AgentFactory) -> dict[str, Any]:
    """Run ConversationAgent once and cache the result.

    Uses the factory so the same LLM client + cached instance is used
    across intent / conversation / reply nodes within a single request.
    """
    ca = factory.get("conversation_agent")
    if ca is None:
        return {"action": "none", "reply": "", "facts": {}}
    try:
        result = await asyncio.to_thread(ca.run, context)
        return {
            "action": str(result.get("action", "none")),
            "reply": str(result.get("reply", "")),
            "facts": result.get("facts", {}),
            
            "_llm_proposal": str(result.get("_llm_proposal", "")),
            "needs_clarification": bool(result.get("needs_clarification", False)),
        }
    except Exception:
        return {"action": "none", "reply": "", "facts": {}, "_llm_proposal": "", "needs_clarification": False}


def _emit_feedback_signal(state: dict) -> dict[str, Any]:
    """Extract FeedbackSignal from grading results for the next request cycle.

    Returns a dict with a ``feedback_signal`` key (or empty dict) suitable
    for merging into the pipeline return value.  The signal is consumed by
    ConversationAgent on the *next* request.
    """
    grading = state.get("grading_result") or {}
    if not isinstance(grading, dict):
        return {}
    error_type = str(grading.get("error_type", "")).strip()
    if not error_type or error_type == "null":
        return {}
    from app.schemas.feedback import FeedbackSignal
    signal = FeedbackSignal.from_grading_result(grading)
    return {"feedback_signal": signal}


async def _run_chat_only(state: dict, factory: AgentFactory) -> dict:
    """处理纯聊天流程（不走 Agent 管线），带 persona 注入能力。"""
    profile_facts = state.get("profile_facts", {}) or {}
    profile_context = ""
    persona_context = ""
    try:
        from app.services.conversation_state import conversation_store as _cs7
        _s7 = _cs7.get(state.get("session_id", ""))
        if _s7 and (_s7.path_planning_info_mode or _s7.profile_extraction_enabled):
            profile_context = _build_profile_context(profile_facts)
            # v1.2: 教材上下文注入（_run_chat_only 是规划模式对话的实际回复路径）
            textbook_ctx = str(state.get("textbook_context") or "").strip()
            textbook_title = ""
            if textbook_ctx:
                import re as _re
                _m = _re.search(r"课本[：:]\s*(.+)$", textbook_ctx, _re.MULTILINE)
                textbook_title = _m.group(1).strip() if _m else ""
                if profile_context:
                    profile_context = profile_context + "\n\n【教材信息】\n" + textbook_ctx
                else:
                    profile_context = "【教材信息】\n" + textbook_ctx
            persona_context = _build_chat_persona(profile_facts, textbook_title=textbook_title)
            if textbook_ctx and persona_context:
                persona_context = persona_context + "\n\n【教材参考】\n" + textbook_ctx
    except Exception:
        pass
    user_msg = state.get("user_message", "")
    reply = ""
    try:
        reply, reply_source = await _chat_provider_reply(
            user_msg, state.get("messages", []) or [], profile_context, persona_context,
        )
        if reply:
            state["reply_source"] = reply_source
    except Exception:
        reply = ""
    if not _is_usable_chat_reply(reply, user_msg):
        reply = _profile_query_reply(user_msg, state.get("profile_v2"), profile_facts)
        if reply:
            state["reply_source"] = "profile_query"
        else:
            reply, fallback_meta = _chat_fallback_reply(user_msg, state.get("messages"))
            state.update(fallback_meta)
            state["fallback_used"] = True
            state["reply_source"] = "chat_fallback"
    state["final_reply"] = reply

    # 画像增量重建
    try:
        from app.services.conversation_state import conversation_store as _cs8
        cs = _cs8.get(state.get("session_id", ""))
        if cs and cs.profile_dirty:
            updated_facts = list(cs.last_updated_fields)
            existing_profile = state.get("profile", {}) or {}
            profile_agent = factory.get("profile_agent")
            if profile_agent:
                pr = profile_agent.run({
                    "session_id": state.get("session_id", ""),
                    "user_message": user_msg,
                    "profile_facts": dict(cs.facts),
                    "course": state.get("course"),
                    "_profile_dirty": True,
                    "_existing_profile": existing_profile,
                    "_updated_facts": updated_facts,
                })
                if pr and pr.get("profile"):
                    state["profile"] = pr["profile"]
                    state["profile_v2"] = pr.get("profile_v2", {})
                    cs.last_result = dict(cs.last_result or {})
                    cs.last_result["profile"] = pr["profile"]
                    cs.last_result["profile_v2"] = pr.get("profile_v2", {})
                    cs.profile_dirty = False
    except Exception:
        pass

    state["pipeline_executed"] = True
    state["overall_status"] = "completed"
    return dict(state)


# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph nodes
# ═══════════════════════════════════════════════════════════════════════════════


async def _intent_node(state: dict) -> dict:
    """Classify user intent via ConversationAgent (once, cached in factory)."""
    factory: AgentFactory = state.get("_factory")
    if factory is None:
        state.setdefault("agent_steps", []).append({"node": "intent_router", "error": "no_factory"})
        state["intent"] = "none"
        return state

    # If intent already provided by upstream caller, skip classification
    if state.get("intent") in ("full_workflow",):
        state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
        return state

    ca_result = await _run_conversation_agent({
        "user_message": state.get("user_message", ""),
        "profile_facts": state.get("profile_facts", {}),
        "conversation_history": state.get("messages", []),
        "feedback_signal": state.get("feedback_signal"),
    }, factory)

    state["intent"] = ca_result["action"]
    state["_conversation_reply"] = ca_result["reply"]
    state["_conversation_facts"] = ca_result["facts"]
    pass  # plan_mode/path_mode removed — unified planner
    state.setdefault("agent_steps", []).append({"node": "intent_router", "intent": state["intent"]})
    logger.info("Intent: %s", state["intent"])
    return state


async def _conversation_node(state: dict) -> dict:
    """Handle chat-only intents."""
    msg = state.get("user_message", "")
    reply = state.get("_conversation_reply", "")

    # Video/animation → native async DeepTutor
    if any(kw in msg for kw in ["视频","动画","微课","短片"]):
        try:
            reply = await deeptutor.chat(
                f"为'{msg}'生成教学视频脚本。包含片头、核心讲解场景、片尾。标注时间轴。2000字以上。",
                state.get("messages", []) or [],
            )
            if reply and len(reply) > 100:
                state["final_reply"] = reply
                state.setdefault("agent_steps", []).append({"node": "conversation_video"})
                return state
        except Exception:
            pass

    # Always use persona-aware DeepTutor for chat intents so probing
    # instructions reach the model every turn.  The ConversationAgent's
    # pre-generated reply is kept as a fallback.
    try:
        profile_facts = state.get("profile_facts", {}) or {}

        # ── 自由学习不注入探针；规划模式（含明确规划意图）才追问 ──
        profile_context = ""
        persona_context = ""
        _need_probe = False
        intent = state.get("intent", "")
        if intent in ("plan", "full_workflow"):
            _need_probe = True
        try:
            from app.services.conversation_state import conversation_store as _cs
            _s = _cs.get(state.get("session_id", ""))
            if _s and (_s.path_planning_info_mode or _s.profile_extraction_enabled):
                _need_probe = True
        except Exception:
            pass
        if _need_probe:
            profile_context = _build_profile_context(profile_facts)
            # v1.2: 教材信息注入 persona 和 profile 上下文
            textbook_ctx = str(state.get("textbook_context") or "").strip()
            textbook_title = ""
            if textbook_ctx:
                # 从 textbook_context 字符串中提取教材标题（第一行格式为"当前科目关联的课本：XXX"）
                import re as _re
                _m = _re.search(r"课本[：:]\s*(.+)$", textbook_ctx, _re.MULTILINE)
                textbook_title = _m.group(1).strip() if _m else ""
                # 注入到 profile_context（作为 memory_context 的一部分）
                if profile_context:
                    profile_context = profile_context + "\n\n【教材信息】\n" + textbook_ctx
                else:
                    profile_context = "【教材信息】\n" + textbook_ctx
            persona_context = _build_chat_persona(profile_facts, textbook_title=textbook_title)
            # 将教材摘要追加到 persona 末尾
            if textbook_ctx and persona_context:
                persona_context = persona_context + "\n\n【教材参考】\n" + textbook_ctx

        dt_reply, reply_source = await _chat_provider_reply(
            msg, state.get("messages", []) or [], profile_context, persona_context,
        )
        if dt_reply:
            reply = dt_reply
            state["reply_source"] = reply_source
    except Exception:
        pass  # keep the pre-existing reply as fallback
    if not _is_usable_chat_reply(reply, msg):
        reply = _profile_query_reply(msg, state.get("profile_v2"), state.get("profile_facts", {}))
        if reply:
            state["reply_source"] = "profile_query"
        else:
            reply, fallback_meta = _chat_fallback_reply(msg, state.get("messages"))
            state.update(fallback_meta)
            state["fallback_used"] = True
            state["reply_source"] = "chat_fallback"
    state["final_reply"] = reply

    state.setdefault("agent_steps", []).append({"node": "conversation"})
    return state


async def _reply_node(state: dict) -> dict:
    """Summarize pipeline results in natural language."""
    path = state.get("learning_path") or []
    resources = state.get("resources") or []
    parts = []
    if path:
        parts.append(f"已生成{len(path)}个学习阶段")
    if resources:
        parts.append(f"配套{len(resources)}个资源")
    summary = "、".join(parts) if parts else "生成流程已完成"
    try:
        reply = await deeptutor.chat(
            f"后端执行完成：{summary}。请用自然语气告知学生结果。",
            state.get("messages", []) or [],
        )
        state["final_reply"] = reply or summary
    except Exception:
        state["final_reply"] = summary
    state.setdefault("agent_steps", []).append({"node": "reply"})
    return state


# ── Pipeline agent nodes ──────────────────────────────────────────────


async def _profile_node(state: dict) -> dict:
    return await _run_agent("profile", state, state["_factory"])

async def _knowledge_node(state: dict) -> dict:
    return await _run_agent("knowledge", state, state["_factory"])

async def _diagnosis_node(state: dict) -> dict:
    return await _run_agent("diagnosis", state, state["_factory"])

async def _plan_node(state: dict) -> dict:
    # ── 硬门槛：只有从路径页确认按钮来的才执行 Planner ──
    # 对话里即便说了"帮我规划"也不运行，只引导到路径页
    try:
        from app.services.conversation_state import conversation_store as _cs5
        _s5 = _cs5.get(state.get("session_id", ""))
        _planning = _s5 and _s5.path_planning_info_mode
    except Exception:
        _planning = False
    if _planning:
        return await _run_agent("planner", state, state["_factory"])
    state["final_reply"] = (
        "好的！请到「学习路径」页面进行设置和生成，那里可以：\n"
        "• 选择规划模式（教材式/日课式/精进式）\n"
        "• 设定总天数和周末安排\n"
        "• 在对话中收集学习信息再生成专属计划\n\n"
        "点击左侧菜单的「学习路径」进入吧～"
    )
    state["pipeline_executed"] = True
    state["overall_status"] = "completed"
    return state

async def _resource_node(state: dict) -> dict:
    return await _run_agent("resource", state, state["_factory"])

async def _question_node(state: dict) -> dict:
    return await _run_agent("question", state, state["_factory"])

async def _review_node(state: dict) -> dict:
    return await _run_agent("review", state, state["_factory"])

async def _grading_node(state: dict) -> dict:
    return await _run_agent("grading", state, state["_factory"])


# ═══════════════════════════════════════════════════════════════════════════════
# Graph construction — uses IntentRouter for edge definitions
# ═══════════════════════════════════════════════════════════════════════════════


def _route_by_intent(state: dict) -> str:
    """Route from intent_router → the appropriate LangGraph node."""
    intent = state.get("intent", "none")
    # 规划模式下，只有 path_planning_info_mode 开启才走 agent 路径
    # 否则让 DeepTutor 自然追问收集信息
    if intent in ("plan", "full_workflow"):
        try:
            from app.services.conversation_state import conversation_store as _cs6
            _s6 = _cs6.get(state.get("session_id", ""))
            if not (_s6 and _s6.path_planning_info_mode):
                return "conversation"
        except Exception:
            return "conversation"
    return get_node_route(intent)


def build_unified_graph() -> StateGraph:
    """Build the full LangGraph state graph.

    Node names and edge targets are derived from IntentRouter so that
    adding a new intent only requires updating intent_router.py.
    """
    g = StateGraph(dict)
    g.set_entry_point("intent_router")

    # All possible nodes
    nodes = [
        ("intent_router", _intent_node),
        ("conversation", _conversation_node),
        ("reply", _reply_node),
        ("profile", _profile_node),
        ("knowledge", _knowledge_node),
        ("diagnosis", _diagnosis_node),
        ("planner", _plan_node),
        ("resource", _resource_node),
        ("question", _question_node),
        ("review", _review_node),
        ("grading", _grading_node),
    ]
    for name, fn in nodes:
        g.add_node(name, fn)

    # Conditional edges from intent_router → all possible targets
    # "pipeline_start" is an alias that redirects to "profile" (the first full-workflow node)
    edge_targets = {
        "conversation": "conversation",
        "profile": "profile",
        "knowledge": "knowledge",
        "planner": "planner",
        "resource": "resource",
        "question": "question",
        "diagnosis": "diagnosis",
        "grading": "grading",
        "pipeline_start": "profile",
    }
    g.add_conditional_edges("intent_router", _route_by_intent, edge_targets)

    # Terminal / chat edges
    g.add_edge("conversation", END)
    g.add_edge("reply", END)

    # NOTE: "question" and "grading" nodes are intentionally NOT in the full-workflow
    # pipeline edges below. They are reached only via the single-agent shortcut path
    # (intent_router → run_pipeline single-agent branch). This is by design:
    # question generation and grading are on-demand actions triggered by explicit
    # user intent, not automatic pipeline stages.
    #
    # Pipeline edges (fixed order for full_workflow)
    g.add_edge("profile", "knowledge")
    g.add_edge("knowledge", "diagnosis")
    g.add_edge("diagnosis", "planner")
    g.add_edge("planner", "resource")
    g.add_edge("resource", "review")
    g.add_conditional_edges("review", _resolve_retry_route, {"reply": "reply", "resource": "resource"})

    return g


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════


def _stringify_items(items: Any, limit: int = 3) -> list[str]:
    if not isinstance(items, list):
        return []
    values: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            value = item.get("topic") or item.get("knowledge_point") or item.get("name") or item.get("title") or item.get("label")
        else:
            value = item
        value = str(value or "").strip()
        if value:
            values.append(value)
    return values


def _diagnosis_reply(diagnosis: Any) -> str:
    if not isinstance(diagnosis, dict):
        return ""
    summary = str(diagnosis.get("diagnosis_summary") or diagnosis.get("summary") or "").strip()
    weak_points = _stringify_items(diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics"))
    next_actions = _stringify_items(diagnosis.get("recommended_next_actions") or diagnosis.get("next_actions"), limit=2)
    parts = [summary or "已完成薄弱点诊断。"]
    if weak_points:
        parts.append("重点关注：" + "、".join(weak_points) + "。")
    if next_actions:
        parts.append("下一步建议：" + "；".join(next_actions) + "。")
    return "".join(parts)


async def run_pipeline(**kwargs) -> dict[str, Any]:
    """Run the full agent pipeline (or single-agent shortcut).

    This is the single entry point called by agent_service and chat_router.
    Internally it uses AgentFactory for lazy agent creation and IntentRouter
    for intent → agent mapping.

    ``_ai_config``: optional per-user AI credential snapshot — pass it when
    the pipeline may outlive the request context (SSE generators, workflow
    threads); otherwise credentials resolve via the request ContextVar.
    """
    factory = AgentFactory(config=kwargs.get("_ai_config"))

    # ── 未配置密钥闸口：不 mock、不规则回退产出内容，直接引导去系统设置 ──
    # 各 agent 内部的规则回退是为真实调用的偶发失败兜底的；密钥缺失属于
    # 用户可自助解决的配置问题，必须在管线入口以 AIConfigMissingError 冒出
    # （HTTP 409 / SSE 错误事件），否则会静默生成与 AI 无关的占位内容。
    from app.services.llm_client import UnconfiguredLLMClient
    from app.utils.errors import AIConfigMissingError
    if isinstance(factory.llm, UnconfiguredLLMClient):
        raise AIConfigMissingError(service="llm")

    state: dict[str, Any] = dict(**kwargs, _retry_count=0, _factory=factory)


    # ── 确保评估调度器在运行（延迟启动兜底）──
    from app.services.assessment_loop import ensure_scheduler_running
    ensure_scheduler_running()

    # ── Intent classification (if not already provided) ──
    intent = state.get("intent", "")
    if not intent:
        # If there's a pending proposal (e.g. last round was <proposal>plan</proposal>),
        # even a short reply like "可以" might be a confirmation — never skip CA.
        from app.services.conversation_state import conversation_store
        pending_proposal = conversation_store.get(state.get("session_id", "")).last_proposal
        msg = str(state.get("user_message", "")).strip()
        if not pending_proposal and _is_likely_chat(msg, state.get("profile_facts", {})):
            intent = "none"
        else:
            ca_result = await _run_conversation_agent({
                "user_message": msg,
                "profile_facts": state.get("profile_facts", {}),
                "conversation_history": state.get("messages", []),
                "feedback_signal": state.get("feedback_signal"),
            }, factory)
            intent = ca_result["action"]
            pass
    state["intent"] = intent

    # ── Chat-only intents — go straight to DeepTutor, no agent overhead ──
    if intent in chat_only_intents():
        return await _run_chat_only(state, factory)

    # ── Single-agent shortcut ──

    # ── Single-agent shortcut ──
    # If agents_filter is explicitly provided (from product.py multi-action dispatch),
    # use it directly; otherwise derive agent_ids from intent.
    agents_filter = state.pop("agents_filter", None)
    agent_ids = agents_filter if (agents_filter is not None and len(agents_filter) > 0) else get_agent_ids(intent)
    if agent_ids is not None and len(agent_ids) > 0:
        # ── 画像收集模式：拦截规划意图，退回聊天 ──
        # 路径规划页面「去对话收集信息」按钮启用此模式，chat 只收集画像不触发规划器
        if "planner_agent" in agent_ids:
            try:
                from app.services.conversation_state import conversation_store as _cs7
                _s7 = _cs7.get(state.get("session_id", ""))
                _collecting = _s7 and _s7.path_planning_info_mode
            except Exception:
                _collecting = False

            if _collecting:
                # 画像收集模式：不触发规划器，退回聊天让 persona 收集信息
                state["intent"] = "none"
                logger.info("path_planning_info_mode=True, overriding plan intent to chat for session=%s",
                            state.get("session_id", ""))
                return await _run_chat_only(state, factory)
            elif kwargs.get("chat_mode") == "planning":
                # 规划模式对话走画像收集，不阻塞
                pass
            elif not kwargs.get("is_workflow"):
                logger.info("Planner blocked in chat mode (is_workflow=False), redirecting to path page. kwargs_keys=%s",
                            [k for k in kwargs if not k.startswith('_')])
                # 普通对话：规划器不通过对话触发，一律引导到路径页面
                # 但 workflow 触发的路径生成（如路径页确认生成按钮）正常执行
                state["final_reply"] = (
                    "好的！请到「学习路径」页面进行设置和生成，那里可以：\n"
                    "• 选择规划模式（教材式/日课式/精进式）\n"
                    "• 设定总天数和周末安排\n"
                    "• 在对话中收集学习信息再生成专属计划\n\n"
                    "点击左侧菜单的「学习路径」进入吧～"
                )
                state["pipeline_executed"] = True
                state["overall_status"] = "completed"
                return dict(state)
            # 规划器只能从路径页面确认生成按钮触发

        # Snapshot old results so we only report what's newly generated
        old_path = len(state.get("learning_path") or [])
        old_res = len(state.get("resources") or [])
        old_qs = len(state.get("questions") or [])

        # ── Load existing path for adjustment mode ──
        if False:  # adjust mode merged into planner
            from app.db.engine import SessionLocal
            from app.db.repository import get_latest_learning_path
            try:
                db = SessionLocal()
                existing = get_latest_learning_path(db, state.get("session_id", ""))
                if existing and existing.stages:
                    state["existing_path"] = {
                        "stages": existing.stages,
                        "id": existing.id,
                    }
            except Exception:
                pass
            finally:
                db.close()

        progress_cb = state.get("progress_callback")
        for full_id in agent_ids:
            short_key = full_id.replace("_agent", "")
            if factory.has(full_id):
                if progress_cb:
                    try: progress_cb(full_id, "running")
                    except Exception: pass
                await _run_agent(short_key, state, factory)
                if progress_cb:
                    try: progress_cb(full_id, "completed")
                    except Exception: pass

        # Explicit path-adjustment requests create a proposal, never replace the
        # active path or start resource generation.
        adjustment_words = ("调整路径", "调整计划", "重新规划", "重新调整", "不适合我", "后面的学习任务")
        if intent == "plan" and any(word in str(state.get("user_message", "")) for word in adjustment_words):
            from app.db.engine import SessionLocal
            from app.db.repository import get_latest_learning_path
            from app.services.conversation_state import conversation_store
            from app.services.day_planner import compute_diff
            db = SessionLocal()
            try:
                active = get_latest_learning_path(db, state.get("session_id", ""))
                proposed = state.get("learning_path") or []
                if active and active.stages and proposed and proposed != active.stages:
                    pending = conversation_store.get_pending_revision(state["session_id"])
                    if pending:
                        proposal = pending
                    else:
                        conversation_store.set_pending_revision(
                            state["session_id"], proposed, compute_diff(active.stages, proposed),
                            reason="用户明确请求调整学习路径", path_id=active.id,
                            subject_id=str(active.session.subject_id or ""),
                            trigger_source="user_request",
                            trigger_id=str(state.get("message_id") or state.get("operation_id") or state.get("user_message", "")),
                        )
                        proposal = conversation_store.get_pending_revision(state["session_id"])
                    state["learning_path"] = active.stages
                    state["revision_proposal"] = {
                        "revisionId": proposal["revision_id"], "pathId": active.id,
                        "status": "pending", "reason": proposal.get("reason", ""),
                        "triggerSource": "user_request", "changedStages": proposal.get("diff", {}).get("changed_stages", []),
                        "changedTasks": proposal.get("diff", {}).get("changed_tasks", []),
                        "currentRevision": active.current_version, "proposedRevision": active.current_version + 1,
                        "requiresUserConfirmation": True,
                    }
            finally:
                db.close()

        # ── 单 agent 路径的审核闭环 ──
        # 跑了 resource_agent 后自动追加 review_agent，发现问题就重试修正
        # 不依赖全量图（图很少被触发），确保所有资源生成都经过审核
        if "resource_agent" in agent_ids:
            """ResourceAgent 审核闭环：只关注资源相关的 check，不因 profile/path 等无关项重试。"""
            resource_check_ids = {"resource_content_quality", "resource_coverage", "resource_type_match", "semantic_quality"}
            retries = state.get("_retry_count", 0)
            max_retries = 1  # was 2 — one retry is enough
            while retries <= max_retries:
                await _run_agent("review", state, factory)
                review = state.get("review", {})
                checks = review.get("checks", [])
                has_resource_issues = any(
                    c.get("check_id") in resource_check_ids
                    and c.get("status") in ("warning", "blocked", "failed")
                    for c in checks
                )
                if not has_resource_issues:
                    break
                if retries >= max_retries:
                    break
                retries += 1
                state["_retry_count"] = retries
                logger.info(
                    "Review flagged resource issues (retry %d/%d), re-running resource_agent",
                    retries, max_retries,
                )
                await _run_agent("resource", state, factory)

        # ── 资源推送：资源审核通过后，自动生成推荐并通知 ──
        # 让用户知道有新的可用资源，无需手动刷新
        if "resource_agent" in agent_ids:
            resources = state.get("resources", []) or []
            if resources:
                try:
                    from app.services.assessment_loop import notification_store
                    from app.services.assessment_loop import AssessmentNotification
                    titles = [r.get("title", "") for r in resources[:3] if r.get("title")]
                    title_str = "、".join(titles)
                    notification_store.push(state.get("session_id", ""), AssessmentNotification(
                        type="recommendations_ready",
                        title="新的学习资源已生成",
                        message=f"已为你生成 {len(resources)} 个学习资源，包括：{title_str}" + ("等" if len(resources) > 3 else ""),
                        session_id=state.get("session_id", ""),
                    ))
                except Exception:
                    pass

        # ── question_agent 审核闭环 ──
        # 题目也经过 review 审核，有问题就重试修正
        if "question_agent" in agent_ids:
            """QuestionAgent 审核闭环：只关注题目相关的 check，不因 profile/path/resource 等无关项重试。"""
            retries = state.get("_retry_count", 0)
            max_retries = 2
            while retries <= max_retries:
                await _run_agent("review", state, factory)
                review = state.get("review", {})
                checks = review.get("checks", [])
                has_question_issues = any(
                    "question" in str(c.get("check_id", ""))
                    and c.get("status") in ("warning", "blocked", "failed")
                    for c in checks
                )
                if not has_question_issues:
                    break
                if retries >= max_retries:
                    break
                retries += 1
                state["_retry_count"] = retries
                logger.info(
                    "Review flagged question issues (retry %d/%d), re-running question_agent",
                    retries, max_retries,
                )
                await _run_agent("question", state, factory)

        state["pipeline_executed"] = True
        state["overall_status"] = "completed"

        # Only report newly generated data (not stale from previous requests)
        path = (state.get("learning_path") or [])[old_path:] if old_path > 0 else state.get("learning_path") or []
        resources = (state.get("resources") or [])[old_res:] if old_res > 0 else state.get("resources") or []
        questions = (state.get("questions") or [])[old_qs:] if old_qs > 0 else state.get("questions") or []
        summary_parts = []
        if path:
            summary_parts.append(f"已生成{len(path)}个学习阶段")
        if resources:
            summary_parts.append(f"配套{len(resources)}个学习资源")
        if questions:
            summary_parts.append(f"生成{len(questions)}道练习题")
        # ── Tutor intent: 生成对话式辅导回复，包含诊断分析和资源引用 ──
        # ── Tutor intent: 先直接回答用户问题，再附上诊断分析和资源推荐 ──
        if "tutor" in intent:
            user_msg = str(state.get("user_message", "")).strip()
            diagnosis = state.get("diagnosis", {})
            resources = state.get("resources", []) or []
            try:
                # 构建带诊断上下文的辅导 prompt
                profile_facts = state.get("profile_facts", {}) or {}
                weak = diagnosis.get("weak_knowledge_points", []) or []
                weak_str = "、".join([w.get("name", "") for w in weak[:3] if w.get("name")])
                tutor_context = f"学生背景：{profile_facts.get('background','')}"
                if profile_facts.get("knowledge_base"):
                    tutor_context += f"，已有基础：{profile_facts['knowledge_base']}"
                if profile_facts.get("learning_goal"):
                    tutor_context += f"，学习目标：{profile_facts['learning_goal']}"
                if weak_str:
                    tutor_context += f"\n薄弱知识点：{weak_str}"
                tutor_prompt = f"{user_msg}\n\n教学参考：{tutor_context}"
                direct_answer = await deeptutor.chat(
                    tutor_prompt,
                    state.get("messages", []) or [],
                )
            except Exception:
                direct_answer = ""
            parts = []
            if direct_answer and len(direct_answer) > 20:
                parts.append(direct_answer.strip())
            weak = diagnosis.get("weak_knowledge_points", []) or []
            if weak:
                names = [w.get("name", "") for w in weak[:3] if w.get("name")]
                parts.append("💡 我注意到你对" + "、".join(names) + "还有一些模糊的地方，下方为你准备了针对性的学习资源。")
            if resources:
                titles = [r.get("title", "") for r in resources[:3] if r.get("title")]
                parts.append("📚 推荐资源：" + "；".join(titles))
            state["final_reply"] = "\n\n---\n\n".join(parts) if parts else (
                str(diagnosis.get("diagnosis_summary") or diagnosis.get("summary", ""))
                or "已经分析了你的问题，并为你准备了对应的学习资源，请查看下方。"
            )
        else:
            diag_reply = _diagnosis_reply(state.get("diagnosis")) if "diagnosis" in intent else ""
            if diag_reply:
                state["final_reply"] = diag_reply
            elif summary_parts:
                state["final_reply"] = "、".join(summary_parts) + "。"
        fb = _emit_feedback_signal(state)
        if fb:
            state.update(fb)
        return dict(state)

    # ── Full workflow ──
    graph = build_unified_graph().compile()
    result = await graph.ainvoke(state, {"recursion_limit": 50})
    result["pipeline_executed"] = True
    result["overall_status"] = "completed"
    retries = result.get("_retry_count", 0)
    if retries >= MAX_RETRIES:
        result["quality_status"] = "warning"
    fb = _emit_feedback_signal(result)
    if fb:
        result.update(fb)
    return dict(result)
