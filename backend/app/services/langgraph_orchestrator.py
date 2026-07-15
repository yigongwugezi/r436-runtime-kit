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
    """After a DeepTutor chat turn, extract any new facts about the student
    and persist them to conversation_store so the profile accumulates over time.
    """
    if not session_id or not user_msg or not assistant_reply:
        return

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
        "你是一个信息提取器。请从以下学生和AI助教的对话中，提取关于学生的任何新事实。\n\n"
        "提取维度：专业/年级背景、想学的课程、已有基础、薄弱点、学习目标、时间安排、学习偏好。\n"
        "规则：\n"
        "- 只提取学生在当前对话中明确说出的信息，不要编造\n"
        "- 提取时尽量具体——'软件工程大二' 优于 '大学生'，'链式法则卡住了' 优于 '数学薄弱'\n"
        "- 如果某个维度在对话中没有新的信息，就空着不填\n\n"
        f"## 当前已知\n{known_block}\n\n"
        f"## 尚未了解\n{unknown_block}\n\n"
        f"## 对话\n学生：{user_msg[:500]}\nAI：{assistant_reply[:600]}\n\n"
        "请输出JSON，只包含从本次对话中新发现的维度（skip已充分了解的维度）：\n"
        '{"updates": {"background": "新值", "target_course": "新值", ...}}'
    )

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
                    "系统学", "专攻", "按章节", "每日学", "每日计划", "薄弱点", "强化"]
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


def _build_chat_persona(facts: dict[str, str]) -> str:
    """Build persona instructions that override DeepTutor's default tutor persona.

    The persona guides DeepTutor through profile-building with per-dimension
    probing strategies — each dimension has its own indirect method, not just
    direct questioning.  Deep understanding of each dimension is the
    prerequisite for true personalisation.
    """
    from app.services.conversation_state import _SHALLOW_PATTERNS

    filled = {k for k, v in facts.items() if v and str(v).strip() and str(v).strip() not in ("未提及", "待补充", "未知", "", "无")}
    total = len(_LABEL_MAP)

    # Detect shallow vs deep per dimension
    shallow_keys: set[str] = set()
    deep_keys: set[str] = set()
    for k in filled:
        val = str(facts.get(k, "")).strip()
        if len(val) < 8 or any(p in val for p in _SHALLOW_PATTERNS if len(val) < len(p) + 8):
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
            "每轮聚焦 1-2 个维度深入了解，不要急着跳到生成。把学生当一个真实的人来了解。"
        )
    elif deep_pct < 0.7:
        stage_guidance = (
            "你对学生有了基本了解，但离真正的个性化规划还差得远。\n"
            "现在重点是：把模糊的回答变具体，把直接询问变为间接探测。\n"
            "每个核心维度至少经过 1 轮追问才算真正了解。"
        )
    elif deep_pct < 1.0 or shallow_keys:
        stage_guidance = (
            "你对学生的了解已经比较全面了。现在要做的是：\n"
            "1. 回顾已了解的信息，用你自己的话总结并向学生确认\n"
            "2. 对仍然模糊的维度做最后一轮追问\n"
            "3. 确认后，才可以提议生成"
        )
    else:
        course = str(facts.get("target_course", ""))
        is_lang = any(w in course for w in ["英语", "日语", "韩语", "法语", "德语", "语言", "雅思", "托福"])
        mode_hint = ""
        if course:
            mode_hint = (
                "\n\n当你觉得学生对你的了解确认无误后，输出：\n"
                "[[mode-pick:教材式,日课式,精进式|course:{course}|default:"
                + ("日课式" if is_lang else "教材式") +
                "]]\n"
            )
        return (
            "你对学生的学习情况已经有了比较深入的了解。\n\n"
            "1. 用自然对话的语气总结关键信息，向学生确认是否准确\n"
            "2. 问学生还有什么补充\n"
            "3. 确认后引出生成方案的提议"
            + mode_hint
        )

    # ═══════════════════════════════════════════════════════════════════
    # Assemble the final persona
    # ═══════════════════════════════════════════════════════════════════
    parts = [
        stage_guidance,
        "",
        "━━━ 本轮聚焦探测的维度 ━━━",
        probing_sections,
    ]
    if other_shallow:
        parts.append(f"\n⚠️ 以下维度回答太模糊，后续需要追问：{'、'.join(_LABEL_MAP.get(k, k) for k in other_shallow)}")
    if other_missing:
        parts.append(f"尚未了解：{'、'.join(_LABEL_MAP.get(k, k) for k in other_missing)}")
    parts.append("\n记住：深入了解每个维度是生成个性化方案的前提。不要急着跳到生成。")
    parts.append(
        "\n⚠️ 一次只深入一个维度，问一个问题。绝对禁止用 | 分隔多个问题——"
        "那是填表式提问，不是自然对话。学生回答后再自然过渡到下一个维度。"
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
    if quality_status not in ("blocked", "failed"):
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
            "plan_mode": str(result.get("plan_mode", "")),
            "path_mode": str(result.get("path_mode", "")),
        }
    except Exception:
        return {"action": "none", "reply": "", "facts": {}, "plan_mode": "", "path_mode": ""}


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
    plan_mode = ca_result.get("plan_mode", "")
    path_mode = ca_result.get("path_mode", "")
    if plan_mode:
        state["plan_mode"] = plan_mode
    if path_mode:
        state["path_mode"] = path_mode
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
        profile_context = _build_profile_context(profile_facts)
        persona_context = _build_chat_persona(profile_facts)

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
    return await _run_agent("planner", state, state["_factory"])

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
    return get_node_route(state.get("intent", "none"))


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
    """
    factory = AgentFactory()
    state: dict[str, Any] = dict(**kwargs, _retry_count=0, _factory=factory)

    # ── Intent classification (if not already provided) ──
    intent = state.get("intent", "")
    if not intent:
        # Quick keyword check — skip heavy ConversationAgent for obvious chat
        msg = str(state.get("user_message", "")).strip()
        if _is_likely_chat(msg, state.get("profile_facts", {})):
            intent = "none"
        else:
            ca_result = await _run_conversation_agent({
                "user_message": msg,
                "profile_facts": state.get("profile_facts", {}),
                "conversation_history": state.get("messages", []),
                "feedback_signal": state.get("feedback_signal"),
            }, factory)
            intent = ca_result["action"]
            plan_mode = ca_result.get("plan_mode", "")
            path_mode = ca_result.get("path_mode", "")
            if plan_mode:
                state["plan_mode"] = plan_mode
            if path_mode:
                state["path_mode"] = path_mode
    state["intent"] = intent

    # ── Chat-only intents — go straight to DeepTutor, no agent overhead ──
    if intent in chat_only_intents():
        profile_facts = state.get("profile_facts", {}) or {}
        profile_context = _build_profile_context(profile_facts)
        persona_context = _build_chat_persona(profile_facts)
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

        # ── Extract facts from the exchange and persist to conversation state ──
        if reply and user_msg:
            try:
                await _extract_facts_after_chat(
                    state.get("session_id", ""),
                    user_msg,
                    reply,
                    profile_facts,
                )
            except Exception:
                pass

        state["pipeline_executed"] = True
        state["overall_status"] = "completed"
        return dict(state)

    # ── Single-agent shortcut ──
    # If agents_filter is explicitly provided (from product.py multi-action dispatch),
    # use it directly; otherwise derive agent_ids from intent.
    agents_filter = state.pop("agents_filter", None)
    agent_ids = agents_filter if (agents_filter is not None and len(agents_filter) > 0) else get_agent_ids(intent)
    if agent_ids is not None and len(agent_ids) > 0:
        # ── Safety net: planning requested but no mode selected → check readiness first ──
        # ── Planning requested but no mode selected → show mode picker directly ──
        if "planner_agent" in agent_ids and not state.get("plan_mode") and not state.get("path_mode"):
            profile_facts = state.get("profile_facts", {}) or {}
            course = str(profile_facts.get("target_course", ""))
            if course:
                is_lang = any(w in course for w in ["英语","日语","韩语","法语","德语","语言","雅思","托福"])
                default_mode = "日课式" if is_lang else "教材式"
                state["final_reply"] = (
                    f"好的！在生成学习路径之前，先选一下你想要的规划模式吧～\n\n"
                    f"[[mode-pick:教材式,日课式,精进式|course:{course}|default:{default_mode}]]"
                )
                state["pipeline_executed"] = True
                state["overall_status"] = "completed"
                return dict(state)

        # Snapshot old results so we only report what's newly generated
        old_path = len(state.get("learning_path") or [])
        old_res = len(state.get("resources") or [])
        old_qs = len(state.get("questions") or [])

        # ── Load existing path for adjustment mode ──
        if state.get("plan_mode") == "adjust":
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

        for full_id in agent_ids:
            short_key = full_id.replace("_agent", "")
            if factory.has(full_id):
                await _run_agent(short_key, state, factory)

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
