"""
对话核心智能体 — 最高优先级调度中心。
负责理解用户意图、判断是否调用子 Agent、统一生成最终回复。
规则引擎仅作为 LLM 失败时的后台兜底，不直接对用户说话。

v4: ConversationAgent 作为外层总控，Orchestrator 只做执行。
"""

import json
import logging
import re
import time
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

    SYSTEM_PROMPT = """你是 EduAgent，一个专业又温暖的学习助手。你是系统的最高优先级调度中心——你负责理解学生、判断时机、调度子 Agent、并统一生成最终回复。

## 你的定位
你是学生唯一看到和对话的对象。你背后有多个子 Agent（画像分析、诊断、路径规划、资源生成），但它们不直接对学生说话——所有回复由你统一出口。

## 对话原则
1. **自然口语化**：像老师一样说话。严禁："收到指令"、"已处理"、"请选择方向"、"画像完整度"、"当前画像信息如下"、格式化追问清单
2. **不自动生成**：学生说"我想学XXX"只是表达意向，不是要求生成。信息足够时你可以提示"已经可以生成初版了，要开始吗？"，但必须等学生确认后才触发
3. **精准追问**：如果确实缺关键信息，只问最需要的1-2个。同时告诉学生"还缺什么"、"下一步可以怎么做"
4. **有记忆**：理解指代词。画像信息保守合并——新信息补充不覆盖已有，新旧冲突时向学生确认
5. **有温度**：展现共情——"这个地方确实容易搞混"、"别着急，我帮你梳理"
6. **不甩锅**：不说"我无法识别"、"请重新描述"，主动猜测并确认
7. **简短有力**：回复控制在2-4句话，不要长篇大论
8. **诚实**：你只说自己真正做过的事。子 Agent 没有执行就不能说"已生成"

## 好的回复示例
学生："我想学微积分"
回复："好的！微积分是理工科的核心基础课。你之前有接触过吗？比如高中导数？还是完全零基础？每天大概能花多长时间？"

学生："零基础，每天三小时，一个月"
回复："明白了，零基础每天三小时，一个月很充足。这些信息已经可以生成第一版学习方案了，要我现在开始吗？"

学生："可以的"
回复："好的，我现在就帮你生成。<action>full_workflow</action>"

学生："我是大三的，学过C语言"
回复："了解了，软件工程大三，有C语言基础。你想重点学习哪个方向？比如数据结构、算法、操作系统？"

## 差的回复示例（绝对禁止）
- "请选择方向：生成学习画像、规划路径、推荐资源或诊断薄弱点"
- "我无法识别你的意图，请重新描述"
- "收到，已更新学习画像。你可以继续补充薄弱点、学习时间或资源偏好"
- "画像完整度 2/7" 或任何 X/Y 格式的进度数字
- 光说不练——只口头描述计划但不触发 action
- 没有执行子 Agent 却说"已生成"、"已推荐"、"已完成诊断"

## 输出格式
你的回复就是纯自然语言，不需要附加任何标签。系统会根据规则引擎自动判断需要执行哪些后台操作。
你只需要做一个自然的、有帮助的学习助手。

## 好的回复示例
学生："我想学微积分"
回复："好的！微积分是理工科的核心基础课。你之前有接触过吗？比如高中导数？还是完全零基础？每天大概能花多长时间？"

学生："零基础，每天三小时，一个月"
回复："明白了，零基础每天三小时，一个月很充足。这些信息已经可以生成第一版学习方案了，要我现在开始吗？"

学生："可以的"
回复："好的，马上帮你生成！"

学生："我是大三的，学过C语言"
回复："了解了，软件工程大三，有C语言基础。你想重点学习哪个方向？比如数据结构、算法、操作系统？"

## 差的回复示例（绝对禁止）
- "请选择方向：生成学习画像、规划路径、推荐资源或诊断薄弱点"
- "我无法识别你的意图，请重新描述"
- "收到，已更新学习画像。你可以继续补充薄弱点、学习时间或资源偏好"
- "画像完整度 2/7" 或任何 X/Y 格式的进度数字
- "已经生成"/"已推荐"/"已完成诊断"——除非你确定系统已经真实执行了

## 画像信息标签
每次回复末尾输出 <facts> 标签：
<facts>
{"target_course": "微积分", "knowledge_base": "零基础", "time_budget": "1个月，每天3小时", "learning_goal": "期末考试拿高分", "background": "软件工程大一学生", "preference": "喜欢做题"}
</facts>

规则：只包含学生明确说过的信息；课程名必须完整准确；没信息的维度不要包含；每次输出完整画像；用 JSON 格式"""

    FINAL_REPLY_PROMPT = """
## final_reply 模式
你现在处于"最终回复"模式。后端子 Agent 已经执行完毕，你需要基于真实执行结果生成统一回复。

## 规则
1. 你必须基于 <pipeline_result> 中列出的真实执行结果说话
2. Planner 没跑 → 不能说"学习路径已生成"
3. Resource 没跑 → 不能说"资源已推荐"
4. Diagnosis 没跑 → 不能说"已完成诊断"
5. Pipeline 执行失败 → 诚实告知失败原因，不假装成功
6. 回复风格与你的自然对话风格完全一致——不要因为后面有数据就突然变成表格式汇报
7. 做自然总结：阶段分布、资源配套、关键建议——用对话语气，不要用 bullet list 模板

## 循环规则
- 每一步执行后必须产生新的有效状态
- 连续两次没有新增状态 → 停止并向学生说明当前卡点
- 同一子 Agent 重复失败 → 停止并向学生说明
- 最多执行 5 次循环
"""

    def __init__(self, mock_data=None, llm_client=None):
        super().__init__(mock_data=mock_data, llm_client=llm_client)
        self._history: list[dict[str, str]] = []

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """主入口。支持两种模式：
        - mode="intent"（默认）：判断意图，返回 action + 自然语言回复
        - mode="final_reply"：读取 pipeline 执行结果，生成统一最终回复
        """
        mode = str(context.get("mode", "intent"))

        if mode == "final_reply":
            return self._run_final_reply(context)

        return self._run_intent(context)

    def _run_intent(self, context: dict[str, Any]) -> dict[str, Any]:
        """意图判断模式。
        规则引擎先定 action（确定性、可靠），LLM 只负责生成自然语言回复。
        LLM 不需要输出任何 <action> 标签——action 已经由规则引擎决定了。
        """
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

        # ── 第1步：规则引擎定 action（确定性，不会"忘记"）──
        rule_result = self._rule_fallback(user_message, context)
        action = rule_result.get("action", "none")
        needs_clarification = rule_result.get("needs_clarification", False)
        rule_reason = rule_result.get("reason", "")

        # ── 第1.5步：规则吃不准时 → LLM 兜底分类 ──
        if rule_reason == "unclassified_fallback" and self.llm_client:
            llm_action = self._llm_classify_action(user_message, context)
            if llm_action and llm_action != "none":
                action = llm_action

        # ── 第2步：LLM 生成自然语言回复（不管 action 决策）──
        llm_reply = ""
        facts = {}
        llm_retry_count = 0
        try:
            for attempt in range(3):
                try:
                    messages = self._build_reply_messages(user_message, context, action)
                    raw_response = self._call_llm(messages)
                    llm_reply, facts = self._extract_reply_and_facts(raw_response)
                    if llm_reply:
                        break
                except LLMClientError:
                    llm_retry_count = attempt + 1
                    if attempt < 2:
                        time.sleep(0.3 * (attempt + 1))
        except Exception:
            llm_reply = ""

        # ── 第3步：LLM 失败时用极简兜底 ──
        if not llm_reply:
            llm_reply = self._action_reply_fallback(action, user_message, needs_clarification)

        self._save_history(user_message, llm_reply, context)

        result = self._make_result(reply=llm_reply, action=action, facts=facts)
        result["llm_retry_count"] = llm_retry_count
        if needs_clarification:
            result["needs_clarification"] = True
        return result

    def _run_final_reply(self, context: dict[str, Any]) -> dict[str, Any]:
        """最终回复模式：读取 pipeline 真实执行结果，生成统一自然语言回复。"""
        pipeline_result = context.get("pipeline_result", {})
        user_message = str(context.get("user_message", "")).strip()
        if not user_message:
            profile_facts = context.get("profile_facts", {})
            if isinstance(profile_facts, dict):
                user_message = str(profile_facts.get("_raw_user_message", "")).strip()

        self._load_history(context)

        # ── 如果 pipeline 根本没执行，不走 LLM，直接返回事实陈述 ──
        if not pipeline_result.get("pipeline_executed"):
            skip_reason = pipeline_result.get("skip_reason", "未知原因")
            return self._make_result(
                reply=f"生成流程未完整执行（{skip_reason}）。你可以稍后重试或告诉我更具体的学习需求。",
                action="none", facts={}
            )

        # ── 构建 final_reply 上下文 ──
        pipeline_text = self._format_pipeline_result(pipeline_result)

        # ── LLM 调用（最多 3 次重试）──
        MAX_RETRIES = 3
        llm_retry_count = 0

        for attempt in range(MAX_RETRIES):
            try:
                messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT + self.FINAL_REPLY_PROMPT},
                ]
                for m in self._history[-20:]:
                    messages.append(m)
                messages.append({
                    "role": "system",
                    "content": f"以下是后端智能体真实执行结果：\n{pipeline_text}",
                })
                messages.append({
                    "role": "user",
                    "content": f"学生最后说：{user_message}\n\n请根据以上真实执行结果，用自然对话语气告知学生结果。",
                })
                raw_response = self._call_llm(messages)
                reply, _, facts = self._parse_response(raw_response)
                if reply:
                    break
            except (LLMClientError, json.JSONDecodeError):
                llm_retry_count = attempt + 1
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.3 * (attempt + 1))
                    continue
        else:
            # LLM 失败 → 极简事实兜底
            reply = self._minimal_fact_reply(pipeline_result)
            facts = {}

        self._save_history(user_message, reply, context)

        result = self._make_result(reply=reply, action="none", facts=facts or {})
        result["llm_retry_count"] = llm_retry_count
        result["final_reply_owner"] = "conversation_agent"
        return result

    def _format_pipeline_result(self, pr: dict) -> str:
        """将 pipeline 执行结果格式化为 LLM 可读的文本摘要。"""
        lines = []
        agents_run = pr.get("agents_run", [])
        lines.append(f"已执行 Agent: {', '.join(agents_run) if agents_run else '无'}")
        lines.append(f"Pipeline 完整执行: {'是' if pr.get('pipeline_executed') else '否'}")
        lines.append(f"学习路径已生成: {'是' if pr.get('learning_path_created') else '否'}")
        lines.append(f"学习路径阶段数: {pr.get('stage_count', 0)}")
        if pr.get("stage_titles"):
            lines.append(f"阶段标题: {', '.join(str(t) for t in pr['stage_titles'][:8])}")
        lines.append(f"资源已生成: {'是' if pr.get('resources_created') else '否'}")
        lines.append(f"资源数量: {pr.get('resource_count', 0)}")
        if pr.get("estimated_days"):
            lines.append(f"预估学习天数: {pr['estimated_days']}")
        lines.append(f"诊断已执行: {'是' if pr.get('diagnosis_created') else '否'}")
        if pr.get("planner_metadata"):
            meta = pr["planner_metadata"]
            if isinstance(meta, dict):
                risk = meta.get("risk_flags", [])
                if risk:
                    lines.append(f"风险标记: {', '.join(str(r) for r in risk)}")
        skip_reason = pr.get("skip_reason", "")
        if skip_reason:
            lines.append(f"跳过原因: {skip_reason}")
        fallback_used = pr.get("fallback_used", False)
        if fallback_used:
            lines.append("注意: 部分 Agent 使用了规则兜底而非 LLM 生成")
        return "\n".join(lines)

    @staticmethod
    def _minimal_fact_reply(pipeline_result: dict) -> str:
        """极简事实兜底——仅在 LLM 完全不可用时使用。"""
        parts = []
        if pipeline_result.get("learning_path_created"):
            parts.append(f"已生成 {pipeline_result.get('stage_count', 0)} 个学习阶段")
        if pipeline_result.get("resources_created"):
            parts.append(f"已生成 {pipeline_result.get('resource_count', 0)} 个学习资源")
        if pipeline_result.get("diagnosis_created"):
            parts.append("已完成诊断分析")
        if not parts:
            return "生成流程已完成。你可以到学习路径和资源库页面查看结果。"
        return "、".join(parts) + "。你可以到对应页面查看详细内容。"

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

    def _build_reply_messages(self, user_message: str, context: dict, action: str) -> list[dict]:
        """构建 LLM 回复生成的消息。action 由规则引擎预先决定，LLM 只管说话。"""
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        for m in self._history[-20:]:
            msgs.append(m)
        ctx_text = self._format_context(context)
        if ctx_text:
            msgs.append({"role": "system", "content": f"当前学生状态：\n{ctx_text}"})

        # 根据预定的 action 告诉 LLM 接下来会发生什么
        action_hints = {
            "full_workflow": "系统将启动完整的学习方案生成流程（画像分析→知识检索→诊断→路径规划→资源生成）。",
            "plan": "系统将启动学习路径规划。",
            "resources": "系统将启动资源推荐和生成。",
            "diagnose": "系统将启动薄弱点诊断分析。",
            "profile": "系统将更新学习画像。",
            "knowledge": "系统将检索课程知识。",
            "none": "",
            "unsafe": "",
        }
        hint = action_hints.get(action, "")
        user_prompt = user_message
        if hint:
            user_prompt = f'{user_message}\n\n[系统提示：已决定执行 action={action}。{hint}你只需简短确认学生的请求，不要说“已生成”——后续 Agent 会真正执行。]'

        msgs.append({"role": "user", "content": user_prompt})
        return msgs

    @staticmethod
    def _extract_reply_and_facts(raw: str) -> tuple[str, dict]:
        """从 LLM 回复中提取文本和画像信息。不再解析 action 标签。"""
        text = raw.strip()
        facts = {}

        # 提取 facts
        facts_match = re.search(r'<facts>(.*?)</facts>', text, re.DOTALL)
        if facts_match:
            try:
                facts = json.loads(facts_match.group(1).strip())
            except json.JSONDecodeError:
                pass
            text = re.sub(r'<facts>.*?</facts>', '', text, flags=re.DOTALL).strip()

        return text, facts

    def _llm_classify_action(self, user_message: str, context: dict) -> str | None:
        """规则引擎吃不准时，用 LLM 做意图分类。只返回 action 字符串，不生成回复。"""
        history_text = "\n".join(
            f"{'学生' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
            for m in self._history[-6:]
        )
        prompt = f"""判断学生最后一条消息的意图，只返回一个 action 标签。

可选 action：
- full_workflow：学生明确要求生成完整学习方案
- diagnose：学生要求诊断薄弱点或有错题
- plan：学生要求规划学习路径
- resources：学生要求推荐或生成学习资源
- none：纯闲聊、补充信息、表达意向

对话历史：
{history_text}

学生消息：{user_message}

只输出一个词（full_workflow/diagnose/plan/resources/none）："""
        try:
            raw = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20,
            )
            raw = raw.strip().lower()
            valid = {"full_workflow", "diagnose", "plan", "resources", "none"}
            for action in valid:
                if action in raw:
                    return action
        except Exception:
            pass
        return None

    @staticmethod
    def _action_reply_fallback(action: str, message: str, needs_clarification: bool) -> str:
        """LLM 不可用时的极简回复。"""
        if needs_clarification:
            return "你是想让我开始生成学习方案，还是继续补充信息？"
        if action == "full_workflow":
            return "好的，我现在就帮你生成学习方案。"
        if action == "resources":
            return "好的，我来帮你生成学习资源。"
        if action == "diagnose":
            return "好的，我来帮你分析薄弱点。"
        if action == "plan":
            return "好的，我来帮你规划学习路径。"
        if action == "profile":
            return "收到，已记录你的信息。"
        return "好的，有什么我可以帮你的？"

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

        if any(w in text for w in ["资源", "资料", "练习", "题", "推荐"]):
            return self._fallback_result("resources", "resource_request")

        if any(w in text for w in ["薄弱", "诊断", "不会", "不懂", "哪里差"]):
            return self._fallback_result("diagnose", "diagnosis_request")

        if any(w in text for w in ["规划", "计划", "路径", "安排", "怎么学", "方案"]):
            return self._fallback_result("full_workflow", "planning_request")

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
            "reply_source": "conversation_agent",
            "final_reply_owner": "conversation_agent",
            "fallback_used": False,
            "llm_retry_count": 0,
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
