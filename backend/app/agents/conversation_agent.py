"""
对话核心智能体 — LLM 直接理解用户意图并生成自然回复。
替代原来 IntentAgent 的规则分类 + 模板回复。
规则引擎降级为安全检查和 LLM 失败时的兜底。

v3: LLM 输出 <facts> 标签，统一管理画像信息。
"""

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)

HIGH_RISK_KEYWORDS = {"作弊", "代考", "代写", "破解", "攻击", "违法", "绕过检测"}
EXACT_CASUAL = {
    "你好", "您好", "hi", "hello", "在吗", "谢谢", "感谢",
    "好的", "好", "明白了", "知道了", "你是谁", "介绍一下",
}


class ConversationAgent(BaseAgent):
    agent_id = "conversation_agent"
    agent_name = "对话智能体"

    SYSTEM_PROMPT = """你是 EduAgent，一个专业又温暖的学习助手。你像一位有经验的私人教师——能听懂学生的各种表达方式，会自然对话，不会让学生觉得在和机器人聊天。

## 你的能力
- 了解学生的学习背景（专业、基础、目标、可用时间）
- 诊断学习薄弱点（分析答题记录、行为数据、学生自述）
- 制定个性化学习计划/路径（根据诊断结果和课程知识库）
- 推荐学习资源（讲义、练习题、思维导图、实操案例等）
- 解答学习困惑（概念解释、学习方法建议）

## 对话原则
1. **自然口语化**：像老师一样说话，不要说"收到指令"、"已处理"、"请选择方向"
2. **主动理解**：即使学生表达不完整，也从上下文推断意图，少问多行动
3. **精准追问**：如果确实缺少关键信息，只问最需要的1-2个问题
4. **有记忆**：理解"这个"、"那个"、"太难了"、"换一个"等指代词
5. **有温度**：展现共情——"这个地方确实容易搞混"、"别着急，我帮你梳理"
6. **不甩锅**：不要说"我无法识别"、"请重新描述"，而是主动猜测并确认
7. **简短有力**：回复控制在2-4句话，不要长篇大论
8. **主动行动**：当信息足够时，主动说"我帮你生成学习方案"，不要等学生说"开始生成"

## 好的回复示例
学生："我想学微积分"
回复："好的！微积分是理工科的核心基础课。你之前有接触过吗？比如高中导数？还是完全零基础？每天大概能花多长时间？"

学生："零基础，每天三小时，一个月"
回复："明白了，零基础每天三小时，一个月很充足。我现在就帮你生成完整的微积分学习方案。<action>full_workflow</action>"

学生："可以的"
回复："好的，我现在就帮你生成具体的学习路径和资源。<action>full_workflow</action>"

## 差的回复示例（绝对禁止）
- "请选择方向：生成学习画像、规划路径、推荐资源或诊断薄弱点"
- "我无法识别你的意图，请重新描述"
- "收到，已更新学习画像。你可以继续补充薄弱点、学习时间或资源偏好"
- 光说不练——只口头描述计划但不触发 action

## 决策标签
在回复末尾，如果需要调用后端智能体生成实际内容，用以下标签标注：
<action>full_workflow</action> — 用户要求生成完整学习方案，或信息已足够（有课程名+时间+基础），或用户说"好的"、"可以"、"生成吧"
<action>diagnose</action>   — 用户要求诊断薄弱点
<action>plan</action>        — 用户只要求规划路径
<action>resources</action>   — 用户只要求推荐资源
<action>none</action>        — 纯聊天、追问信息

## 何时必须触发 <action>full_workflow</action>
1. 学生明确了课程名 + 有时间 + 有基础水平 → 直接行动
2. 学生说"可以"、"好的"、"行"、"生成吧"等确认词 → 立刻行动
3. 你已经口头给出了阶段计划 → 立刻触发正式生成
4. 不要等学生说"开始生成"，你主动判断时机

## 画像信息标签（重要！）
每次回复时，在末尾输出 <facts> 标签，包含你对学生当前完整画像的理解：
<facts>
{"target_course": "微积分", "knowledge_base": "零基础", "time_budget": "1个月，每天3小时", "learning_goal": "期末考试拿高分", "background": "软件工程大一学生", "preference": "喜欢做题"}
</facts>

规则：
- 只包含学生明确说过的信息，不要推测，不要编造
- 课程名必须是完整准确的，如"微积分"、"数据结构"、"Python"，绝对不要提取"的是什么"这种无效值
- 如果某个维度没有信息，就不要包含这个字段
- 每次输出完整的当前画像（包括之前已确认的 + 本轮新增的），不只是增量
- 这是给后端系统用的，用 JSON 格式"""

    def __init__(self, mock_data=None, llm_client=None):
        super().__init__(mock_data=mock_data, llm_client=llm_client)
        self._history: list[dict[str, str]] = []

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        profile_facts = context.get("profile_facts", {})
        if isinstance(profile_facts, dict) and profile_facts.get("_raw_user_message"):
            user_message = str(profile_facts["_raw_user_message"]).strip()
        else:
            user_message = str(context.get("user_message", "")).strip()

        if not user_message:
            return self._make_result(
                reply="你好！我是你的学习助手，有什么可以帮助你的？",
                action="none", facts={}
            )

        safety_check = self._safety_check(user_message)
        if safety_check:
            return safety_check

        self._load_history(context)

        try:
            messages = self._build_llm_messages(user_message, context)
            raw_response = self._call_llm(messages)
            reply, action, facts = self._parse_response(raw_response)
        except LLMClientError:
            fallback = self._rule_fallback(user_message, context)
            reply = fallback.pop("reply", "")
            action = fallback.pop("action", "none")
            facts = {}
            logger.warning("LLM failed, using rule fallback for conversation")

        self._save_history(user_message, reply, context)

        return self._make_result(reply=reply, action=action, facts=facts, extra=fallback if "fallback" in locals() else None)

    def load_history(self, history):
        self._history = history

    def get_history(self):
        return list(self._history)

    def _safety_check(self, message):
        if any(kw in message for kw in HIGH_RISK_KEYWORDS):
            return self._make_result(
                reply="抱歉，我不能协助这类请求。如果你有学习相关的问题，我很乐意帮忙。",
                action="unsafe", facts={}
            )
        return None

    def _build_llm_messages(self, user_message, context):
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        for m in self._history[-20:]:
            msgs.append(m)
        ctx_text = self._format_context(context)
        if ctx_text:
            msgs.append({"role": "system", "content": f"当前学生状态：\n{ctx_text}"})
        msgs.append({"role": "user", "content": user_message})
        return msgs

    def _format_context(self, context):
        parts = []
        profile = context.get("profile", {})
        if profile:
            summary = self._summarize_profile(profile)
            if summary:
                parts.append(f"【学习画像】\n{summary}")
        diagnosis = context.get("diagnosis")
        if isinstance(diagnosis, dict):
            d_parts = []
            weak = diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []
            names = [w.get("name") or w.get("topic") or "" for w in weak if isinstance(w, dict)]
            names = [n for n in names if n and n not in ("无诊断数据", "unknown")]
            if names:
                d_parts.append(f"薄弱点：{'、'.join(names[:5])}")
            summary = diagnosis.get("diagnosis_summary") or diagnosis.get("summary") or ""
            if summary:
                d_parts.append(f"诊断摘要：{summary}")
            if d_parts:
                parts.append("【诊断结果】\n" + "\n".join(d_parts))
        plan = context.get("learning_path") or context.get("stages") or []
        if plan:
            titles = [s.get("title", "") for s in plan[:5] if isinstance(s, dict) and s.get("title")]
            if titles:
                parts.append(f"【学习路径】\n{' → '.join(titles)}")
        resources = context.get("resources") or []
        if resources:
            r_titles = [r.get("title", "") for r in resources[:5] if isinstance(r, dict) and r.get("title")]
            if r_titles:
                parts.append(f"【已有资源】\n" + "\n".join(f"· {t}" for t in r_titles))
        return "\n\n".join(parts)

    def _summarize_profile(self, profile):
        mapping = {
            "身份/专业背景": ["major_background", "identity", "academic_background", "major"],
            "目标课程": ["interest_direction", "target_course", "learning_goal"],
            "当前基础": ["knowledge_base", "current_level"],
            "薄弱点": ["error_patterns", "weak_points"],
            "学习目标": ["learning_goal_knowledge"],
            "时间安排": ["learning_rhythm", "time_budget"],
            "学习偏好": ["cognitive_style", "learning_preference"],
        }
        lines = []
        profile_dict = self._flatten_profile(profile)
        for label, keys in mapping.items():
            for key in keys:
                val = profile_dict.get(key, "").strip()
                if val and val != "未提及":
                    lines.append(f"{label}：{val}")
                    break
        return "\n".join(lines)

    def _flatten_profile(self, profile):
        flat = {}
        for key, item in profile.items():
            if isinstance(item, dict):
                val = str(item.get("value", "")).strip()
                if val:
                    flat[key] = val
            elif item:
                flat[key] = str(item)
        return flat

    def _call_llm(self, messages):
        if not self.llm_client:
            raise LLMClientError("No LLM client configured")
        return self.llm_client.chat(messages=messages, temperature=0.7, max_tokens=800)

    def _parse_response(self, raw: str) -> tuple[str, str, dict]:
        text = raw.strip()
        action = "none"
        facts = {}

        # 提取 action
        action_match = re.search(r'<action>(.*?)</action>', text, re.DOTALL)
        if action_match:
            action = action_match.group(1).strip()
            text = re.sub(r'<action>.*?</action>', '', text, flags=re.DOTALL).strip()

        valid_actions = {"diagnose", "plan", "resources", "profile", "knowledge", "full_workflow", "none", "unsafe"}
        if action not in valid_actions:
            action = "none"

        # 提取 facts
        facts_match = re.search(r'<facts>(.*?)</facts>', text, re.DOTALL)
        if facts_match:
            try:
                facts = json.loads(facts_match.group(1).strip())
            except json.JSONDecodeError:
                pass
            text = re.sub(r'<facts>.*?</facts>', '', text, flags=re.DOTALL).strip()

        return text, action, facts

    def _rule_fallback(self, message, context):
        text = message.strip().lower()
        compact = re.sub(r"\s+", "", text)
        confirm_words = {"可以", "好的", "行", "嗯", "好", "ok", "yes", "对", "是的", "嗯嗯", "没错", "就这样", "按这个来"}
        explicit_generation = (
            any(phrase in compact for phrase in (
                "开始生成学习方案", "帮我生成学习方案", "帮我制定学习计划",
                "给我制定学习路径", "按这些信息生成", "就按这个生成",
                "给我生成学习路径", "生成吧", "开始吧",
            ))
            or (
                any(word in compact for word in ("生成", "制定", "规划", "计划", "路径", "方案"))
                and not re.search(r"(?:想学|想学习|我要学|要学习|学习)\s*[\u4e00-\u9fffA-Za-z+#]{2,12}$", compact)
            )
        )

        if explicit_generation:
            return self._fallback_result("full_workflow", "explicit_generation_request")

        if compact in confirm_words:
            if self._has_generation_confirmation_context(context):
                return self._fallback_result("full_workflow", "contextual_generation_confirmation")
            return self._fallback_result("none", "confirmation_without_generation_context", needs_clarification=True)

        if text in EXACT_CASUAL or len(compact) <= 2:
            return self._fallback_result("none", "short_or_casual_message")

        learn_match = re.search(r'(?:学|学习|入门|复习|想学|要学)\s*([\u4e00-\u9fffA-Za-z+#]{2,12})', text)
        if learn_match:
            return self._fallback_result("none", "learning_intent_collect_profile")

        if any(w in text for w in ["规划", "计划", "路径", "安排", "怎么学", "方案"]):
            return self._fallback_result("full_workflow", "planning_request")

        if any(w in text for w in ["薄弱", "诊断", "不会", "不懂", "哪里差"]):
            return self._fallback_result("diagnose", "diagnosis_request")

        if any(w in text for w in ["资源", "资料", "练习", "题", "推荐"]):
            return self._fallback_result("resources", "resource_request")

        return self._fallback_result("none", "unclassified_fallback")

    def _fallback_result(self, action, reason, needs_clarification=False):
        return {
            "reply": "",
            "action": action,
            "fallback_used": True,
            "reason": reason,
            "debug_reason": reason,
            "needs_clarification": needs_clarification,
            "needs_final_reply": True,
            "final_reply_owner": "conversation_agent",
            "pipeline_required": action not in ("none", "unsafe"),
            "target_agents": ["full_workflow"] if action == "full_workflow" else [],
        }

    def _has_generation_confirmation_context(self, context):
        history = context.get("conversation_history") or self._history
        if not isinstance(history, list):
            return False
        markers = ("生成", "学习方案", "学习计划", "学习路径", "按这些信息", "要开始吗", "开始吗")
        for item in reversed(history[-6:]):
            if not isinstance(item, dict):
                continue
            if item.get("role") not in {"assistant", "system"}:
                continue
            content = str(item.get("content") or "")
            if any(marker in content for marker in markers):
                return True
        return False

    def _load_history(self, context):
        loaded = context.get("conversation_history")
        if isinstance(loaded, list):
            self._history = [m for m in loaded if isinstance(m, dict) and "role" in m and "content" in m]
        else:
            self._history = []

    def _save_history(self, user_msg, reply, context):
        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": reply})
        if len(self._history) > 40:
            self._history = self._history[-40:]
        context["conversation_history"] = list(self._history)

    def _make_result(self, reply, action, facts=None, extra=None):
        result = {
            "reply": reply,
            "action": action,
            "facts": facts or {},
            "intent": self._action_to_intent(action),
            "primary_intent": self._action_to_primary_intent(action),
            "should_run_agents": action not in ("none", "unsafe"),
            "should_run_full_workflow": action == "full_workflow",
            "needs_clarification": False,
            "confidence": 0.85 if action != "none" else 0.9,
            "conversation_history": list(self._history),
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "completed",
                "summary": f"对话完成，action={action}",
                "started_at": None,
                "finished_at": None,
            },
        }
        if extra:
            result.update(extra)
            if "needs_clarification" in extra:
                result["needs_clarification"] = extra["needs_clarification"]
        return result

    def _action_to_intent(self, action):
        return {
            "diagnose": "diagnosis", "plan": "learning_plan", "resources": "resource_request",
            "profile": "profile_update", "knowledge": "learning_plan", "full_workflow": "full_workflow",
            "unsafe": "unsafe", "none": "casual_chat",
        }.get(action, "unknown")

    def _action_to_primary_intent(self, action):
        return {
            "diagnose": "diagnosis", "plan": "learning_plan", "resources": "resource_request",
            "profile": "profile_update", "knowledge": "learning_plan", "full_workflow": "full_workflow",
            "unsafe": "unsafe", "none": "general_chat",
        }.get(action, "unknown")
