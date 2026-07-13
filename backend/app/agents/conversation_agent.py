"""
对话核心智能体 — 最高优先级调度中心。
负责理解用户意图、判断是否调用子 Agent、统一生成最终回复。
规则引擎仅作为 LLM 失败时的后台兜底，不直接对用户说话。

v4: ConversationAgent 作为外层总控，Orchestrator 只做执行。
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from typing import Any

from app.agents.base import BaseAgent, register_agent
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)

HIGH_RISK_KEYWORDS = {"作弊", "代考", "代写", "破解", "攻击", "违法", "绕过检测"}
EXACT_CASUAL = {
    "你好", "您好", "hi", "hello", "在吗", "谢谢", "感谢",
    "好的", "好", "明白了", "知道了", "你是谁", "介绍一下",
}


@register_agent
class ConversationAgent(BaseAgent):
    agent_id = "conversation_agent"
    agent_name = "对话智能体"

    SYSTEM_PROMPT = """你是 EduAgent，一个专业又温暖的学习助手。你是学生唯一对话的对象——你背后有多个子 Agent（画像分析、诊断、路径规划、资源生成、试题生成），但它们不直接对学生说话，所有回复由你统一出口。

## 核心原则
1. **自然口语化**：像朋友聊天一样说话。严禁"收到指令""已处理""请选择方向""画像完整度""当前画像信息如下""已记录你的信息"等机器话术。
2. **深入了解优先于快速生成**：学生说"我想学XXX"只是表达意向。你的首要任务是深入了解学生——背景、基础、目标、卡点、时间、偏好。每个维度不仅要知道"是什么"，还要知道"为什么"和"到什么程度"。个性化方案的精度取决于你了解的深度。
3. **多问、深问、巧问**：按以下维度逐个深入了解，每次聚焦 1 个维度深入挖掘，不要像填表一样罗列问题。
   不要只满足于学生的第一句话——"学过一点"追问具体内容，"基础一般"追问哪个部分一般，"要考试"追问什么考试什么时候。
   - 身份/专业背景（什么专业、年级、方向）
   - 目标课程/方向（想学什么、为什么想学、想学到什么程度）
   - 已有基础（用间接方式探测——让学生解释概念、出简单判断题、追问具体学过什么内容。根据科目适配：微积分问数学基础、编程课问编程基础、英语问当前水平）
   - 薄弱点/卡点（不要直接问"你哪里薄弱"——从学生的提问、卡顿、描述中推断。可以问"之前学的时候哪个部分印象最深？""有没有哪类题经常做错？"）
   - 学习目标（考试/考研/项目/入门，追问具体到什么程度——"期末考及格就行"和"想拿90分"是两种方案）
   - 时间安排（多久、每天多长时间、是连续的还是碎片化的、周末能学吗、是理想时间还是实际可用时间）
   - 学习偏好（喜欢文字讲解、图解、视频还是做题。可以在对话中自然试探——"我用文字解释还是画个图？"）
   注意：编程能力只在计算机相关课程中才需要了解，微积分、英语等课程不要问编程相关问题。
4. **基于当前对话**：只基于学生当前对话中说过的话来回应。不要假装认识学生、不要编造或猜测学生的姓名和专业——除非学生刚刚在当前对话中说过。即使用系统注入了背景信息，也只把它们当作"已知信息"来避免重复询问，不要复述给用户。
5. **精准执行**：学生明确指定了就只做那一件事，不多做。
6. **分步引导**：当你对学生有了足够深入的了解后，按顺序逐一确认：路径(<proposal>plan</proposal>)→资源(<proposal>resources</proposal>)→练习题(<proposal>questions</proposal>)。已有就跳过。不要在学生刚说了两句话就提议生成。
7. **增量优先**：修改现有内容时只调相关 Agent，不重跑全量。
8. **尊重拒绝**：学生说"不要"后不自动触发。
9. **诚实**：没执行就不能说"已生成"。

## 什么时候才提议生成？
以下条件全部满足时，才可以自然地说"我对你的学习情况了解得比较清楚了，要开始生成个性化的学习路径吗？"：
- ✅ 知道了学生的专业/背景
- ✅ 知道了要学什么课程、想学到什么程度
- ✅ 对学生的已有基础有具体了解（不是"学过一点"这种模糊回答——要么追问出了具体内容，要么通过诊断问题验证了水平）
- ✅ 知道了学习目标以及目标的具体程度
- ✅ 知道了可用时间
- ⚠️ 如果以上任何一个维度的回答还是模糊的，继续追问，不要提议生成。

## 标签格式
- 确定学生要什么 → "好的，我来生成<execute>resources</execute>"
- 问学生要不要做什么 → "要生成路径吗？<proposal>plan</proposal>"
- 纯闲聊 → 不加标签

## 示例对话（注意：这是一段深入探测的完整示例，实际对话可能更长）
学生："我想学微积分"
回复："微积分是理工科核心课～你是为了什么想学它？期末考试、考研、还是自己想深入了解？"

学生："期末考，大概还有一个月"
回复："一个月冲刺期末，时间上还行。你之前上课的时候，微积分哪些部分觉得比较顺、哪些部分听着听着就懵了？"

学生："函数和极限那边还凑合，到了导数就开始晕了"
回复："导数确实是微积分的第一个坎。你说的'晕'具体是卡在哪里——是求导公式记不住、复合函数求导搞不清、还是导数的几何意义不太理解？"

学生："复合函数求导，什么链式法则的，看到一大坨套来套去就不知道怎么下手了"
回复："明白了，链式法则是复合函数求导的核心。对了，你是学什么专业的？知道专业背景我可以帮你找更贴切的例子。"

学生："软件工程大二"
回复："软工的话微积分对后面的算法课和机器学习都有用。你每天大概能投入多长时间来学？是每天都能抽出时间还是主要靠周末？"

学生："平时晚上能学一两小时，周末可以多花点时间"
回复："好的，那时间上还是比较充裕的。对了，学习的时候你是更喜欢看文字讲义一步步推、还是喜欢看视频讲解、还是直接做题练手？"

学生："我喜欢先看视频理解概念，然后做题巩固"
回复："视频+练习的组合效率很高。好了，我对你的学习情况了解得比较清楚了——软工大二、一个月冲刺微积分期末、函数极限有基础但链式法则卡住了、每晚一两小时加周末、偏好视频+练习。要开始生成个性化的学习路径吗？<proposal>plan</proposal>"

## 禁止事项
- "请选择方向""画像完整度 X/7""当前画像信息如下""已记录你的信息"
- "收到指令""已处理""已生成"（除非真实执行了）
- "我记得你是……""根据系统记录，你是……"等假装认识学生的话
- 用 | 分隔多个问题——一次只问一件事
- 一次性抛出 3 个及以上问题
- 用表格、列表、多行格式来提问——保持自然对话语气
- 复述系统注入的背景信息——那些是给你参考的，不是给你背的
- 在学生只说了 2-3 句话、画像还很模糊的时候就提议生成"""

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

    @classmethod
    def from_context(
        cls,
        context: dict[str, Any],
        llm_client: Any = None,
    ) -> "ConversationAgent":
        """Get or create a ConversationAgent, reusing if cached in context.

        This avoids redundant instantiation when multiple orchestrator nodes
        need the ConversationAgent within a single request.
        """
        existing = context.get("_conversation_agent_instance")
        if existing is not None:
            return existing
        from app.services.llm_client import get_llm_client
        from app.config import settings
        client = llm_client or get_llm_client(settings.llm_provider)
        agent = cls(mock_data={}, llm_client=client)
        agent._load_history(context)
        context["_conversation_agent_instance"] = agent
        return agent

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

        # ── Store session_id + profile_facts for _try_deeptutor_reply ──
        self._current_session_id = str(context.get("session_id", ""))
        self._current_profile_facts = dict(profile_facts) if isinstance(profile_facts, dict) else {}

        if not user_message:
            return self._make_result(
                reply="你好！我是你的学习助手，有什么可以帮助你的？",
                action="none", facts={}
            )

        safety_check = self._safety_check(user_message)
        if safety_check:
            return safety_check

        self._load_history(context)

        needs_clarification = False

        # ── 规则先定确定性 action；只有兜不住时再让 LLM 猜。 ──
        rule_result = self._rule_fallback(user_message, context)
        rule_action = rule_result.get("action", "none")
        rule_reason = rule_result.get("reason", "")
        needs_clarification = rule_result.get("needs_clarification", False)
        action = rule_action

        # ── Rule engine is authoritative for agent triggers ──
        # The rewritten rule_fallback uses exact multi-word phrase matching
        # and is far more reliable than LLM classification.  We deliberately
        # do NOT fall back to LLM classification here — it was causing
        # false positives like classifying "多放几道例题" as generate_questions.

        llm_reply = ""
        facts = {}
        llm_retry_count = 0

        # Check for explicit FeedbackSignal from previous grading run
        feedback_signal = context.get("feedback_signal")
        if feedback_signal is None:
            from app.schemas.feedback import FeedbackSignal
            raw = context.get("profile_facts", {}).get("_pending_adjustment", "")
            if raw:
                feedback_signal = FeedbackSignal(error_type=raw)
        if feedback_signal and action == "none":
            signal = feedback_signal if isinstance(feedback_signal, FeedbackSignal) else FeedbackSignal.from_dict(feedback_signal) if isinstance(feedback_signal, dict) else None
            if signal and signal.error_type:
                suggestion = f"上次练习中发现了{signal.error_label or signal.error_type}，建议调整学习计划重点强化这部分。要我现在帮你重新规划吗？"
                result = self._make_result(reply=suggestion, action="none", facts={})
                result["needs_clarification"] = False
                # Clear the signal so it only fires once
                context["feedback_signal"] = None
                context.get("profile_facts", {}).pop("_pending_adjustment", None)
                return result

        if action in ("none", "tutoring", "", "deep_tutor_chat"):
            dt_capability = rule_result.get("capability", "chat")
            dt = self._try_deeptutor_reply(user_message, self._history, capability=dt_capability)
            if dt and len(dt) > 5:
                llm_reply = re.sub(r'<[^>]+>', '', dt).strip()

        exec_action = ""
        if not llm_reply:
            try:
                for attempt in range(3):
                    try:
                        messages = self._build_reply_messages(user_message, context, action)
                        raw_response = self._call_llm(messages)
                        llm_reply, facts, exec_action, proposal = self._extract_reply_and_facts(raw_response)
                        if proposal:
                            context["_llm_proposal"] = proposal
                        if llm_reply:
                            break
                    except LLMClientError:
                        llm_retry_count = attempt + 1
                        if attempt < 2:
                            time.sleep(0.3 * (attempt + 1))
            except Exception:
                llm_reply = ""

        # ── execute 标签覆盖规则 action ──
        # LLM 可通过 <execute>resources</execute> 直接触发 Agent 执行。
        # 仅在 exec_action 是有效 action 且当前规则 action 为 none/tutoring 时生效；
        # 若 exec_action 与规则 action 不同且规则 action 已生效，则降级为 proposal。
        VALID_EXECUTE_ACTIONS = {
            "plan", "resources", "generate_questions", "diagnose",
            "grade_answer", "profile", "full_workflow",
            "assess", "tutor",
        }
        if exec_action and exec_action in VALID_EXECUTE_ACTIONS:
            if action in ("none", "tutoring", ""):
                action = exec_action
            elif action != exec_action and not context.get("_llm_proposal"):
                context["_llm_proposal"] = exec_action

        # ── 第3步：LLM 失败时用极简兜底 ──
        if not llm_reply:
            llm_reply = self._action_reply_fallback(action, user_message, needs_clarification)

        self._save_history(user_message, llm_reply, context)

        extra = {}
        plan_mode = rule_result.get("plan_mode", "")
        path_mode = rule_result.get("path_mode", "")
        if plan_mode:
            extra["plan_mode"] = plan_mode
        if path_mode:
            extra["path_mode"] = path_mode
        result = self._make_result(reply=llm_reply, action=action, facts=facts, extra=extra or None)
        result["llm_retry_count"] = llm_retry_count
        if context.get("_llm_proposal"):
            result["_llm_proposal"] = context["_llm_proposal"]
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

        # ── DeepTutor / LLM 生成最终回复 ──
        llm_retry_count = 0
        facts = {}

        # Try DeepTutor first for natural summary
        dt_reply = self._try_deeptutor_reply(
            f"学生最后说：{user_message}\n\n后端生成了以下结果，请用自然对话语气告诉学生：\n{pipeline_text}",
            self._history
        )
        if dt_reply and len(dt_reply) > 10:
            reply = re.sub(r'<[^>]+>', '', dt_reply).strip()
        else:
            # Fall back to LLM
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
                reply = re.sub(r'<proposal>.*?</proposal>', '', reply, flags=re.DOTALL)
                reply = re.sub(r'<execute>.*?</execute>', '', reply, flags=re.DOTALL)
                if not reply:
                    reply = self._minimal_fact_reply(pipeline_result)
            except Exception:
                reply = self._minimal_fact_reply(pipeline_result)

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
        if pr.get("stage_summaries"):
            for s in pr["stage_summaries"][:3]:
                goal_text = str(s.get("goal", ""))
                dur_text = str(s.get("duration", ""))
                detail = f"：{goal_text}（{dur_text}）" if goal_text else ""
                lines.append(f"  阶段「{s.get('title', '')}」{detail}")
        if pr.get("resource_types"):
            lines.append(f"  资源类型: {'、'.join(str(t) for t in pr['resource_types'])}")
        if pr.get("diagnosis_key_finding"):
            lines.append(f"  诊断发现: {pr['diagnosis_key_finding']}")
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
        """构建 LLM 回复消息。LLM 自己决定用 <execute> 或 <proposal>。"""
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        for m in self._history[-20:]:
            msgs.append(m)
        ctx_text = self._format_context(context)
        if ctx_text:
            msgs.append({
                "role": "system",
                "content": (
                    f"【参考信息——仅供你判断还需要了解什么，不要在回复中复述这些内容】\n{ctx_text}"
                ),
            })
        msgs.append({"role": "user", "content": user_message})
        return msgs

    @staticmethod
    def _extract_reply_and_facts(raw: str) -> tuple[str, dict, str, str]:
        """从 LLM 回复中提取文本、画像、execute action、proposal。"""
        text = raw.strip()
        facts = {}
        execute_action = ""
        proposal = ""

        # 提取 proposal（在剥离之前，比 execute 先提取避免混淆）
        prop_match = re.search(r'<proposal>(.*?)</proposal>', text, re.DOTALL)
        if prop_match:
            proposal = prop_match.group(1).strip()
            text = re.sub(r'<proposal>.*?</proposal>', '', text, flags=re.DOTALL)

        # 提取 execute 标签
        exec_match = re.search(r'<execute>(.*?)</execute>', text, re.DOTALL)
        if exec_match:
            execute_action = exec_match.group(1).strip()
            text = re.sub(r'<execute>.*?</execute>', '', text, flags=re.DOTALL)

        # 提取 facts
        facts_match = re.search(r'<facts>(.*?)</facts>', text, re.DOTALL)
        if facts_match:
            try:
                facts = json.loads(facts_match.group(1).strip())
            except json.JSONDecodeError:
                pass
            text = re.sub(r'<facts>.*?</facts>', '', text, flags=re.DOTALL)

        return text.strip(), facts, execute_action, proposal

    def _llm_classify_action(self, user_message: str, context: dict) -> str | None:
        """LLM 优先判 action。理解用户的各种口语表达，返回标准 action 名。"""
        history_text = "\n".join(
            f"{'学生' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
            for m in self._history[-6:]
        )
        # 检查 last_proposal 给 LLM 上下文
        last_proposal = context.get("last_proposal", "")
        proposal_hint = f"\n上一轮系统问了'要{last_proposal}吗'，学生可能是回答这个问题。" if last_proposal else ""

        prompt = f"""判断学生意图，只输出一个词。

可选：full_workflow（明确要求完整方案含路径+资源）、plan（明确要求学习路径）、resources（明确要求资源/资料）、generate_questions（明确要求出题/做题）、diagnose（明确要求诊断薄弱点）、grade_answer（明确要求批改）、none（闲聊/提供信息/表达学习意愿/追问）

关键规则：
- "我想学X""我要学X""我对X感兴趣"等表达学习意愿 → none（先聊天收集信息，不急着生成）
- 必须有明确的"帮我生成""给我做""开始吧""生成方案"等生成请求 → 才是 plan/resources/full_workflow
- "可以""好的""行" → 看上下文是否系统刚问过"要生成吗"{proposal_hint}
- "思维导图""脑图""知识图谱""生成XX图" → resources
- "出题""做题""练习"等明确出题请求 → generate_questions

对话：
{history_text}

学生：「{user_message}」

action："""
        try:
            raw = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20,
            )
            raw = raw.strip().lower()
            valid = {"diagnose", "plan", "resources", "generate_questions", "grade_answer", "none", "assess", "tutor"}
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
            msgs.append({
                "role": "system",
                "content": (
                    f"【参考信息——仅供你判断还需要了解什么，不要在回复中复述这些内容】\n{ctx_text}"
                ),
            })
        msgs.append({"role": "user", "content": user_message})
        return msgs

    def _format_context(self, context):
        """构建上下文摘要——标注已知/缺失，引导 LLM 追问缺口而非复述已知。"""
        parts = []

        # 已知信息
        profile = context.get("profile", {})
        if profile:
            summary = self._summarize_profile(profile)
            if summary:
                parts.append(f"已知：\n{summary}")

        # 缺失维度——提示 LLM 优先追问这些
        profile_facts = context.get("profile_facts", {})
        if isinstance(profile_facts, dict):
            from app.services.conversation_state import PROFILE_FIELD_DEFS
            missing = [
                meta["label"]
                for key, meta in PROFILE_FIELD_DEFS.items()
                if not profile_facts.get(key)
            ]
            if missing:
                parts.append(f"尚未了解：{'、'.join(missing)}")

        diagnosis = context.get("diagnosis")
        if isinstance(diagnosis, dict):
            weak = diagnosis.get("weak_knowledge_points") or diagnosis.get("weak_topics") or []
            names = [w.get("name") or w.get("topic") or "" for w in weak if isinstance(w, dict)]
            names = [n for n in names if n and n not in ("无诊断数据", "unknown")]
            if names:
                parts.append(f"薄弱点：{'、'.join(names[:5])}")

        plan = context.get("learning_path") or context.get("stages") or []
        if plan:
            titles = [s.get("title", "") for s in plan[:5] if isinstance(s, dict) and s.get("title")]
            if titles:
                parts.append(f"学习路径：{' → '.join(titles)}")

        return "\n".join(parts)

    def _summarize_profile(self, profile):
        mapping = {
            "专业背景": ["major_background", "identity", "academic_background", "major"],
            "目标课程": ["interest_direction", "target_course", "learning_goal"],
            "当前基础": ["knowledge_base", "current_level"],
            "薄弱点": ["error_patterns", "weak_points"],
            "学习目标": ["learning_goal_knowledge"],
            "时间安排": ["learning_rhythm", "time_budget"],
            "学习偏好": ["cognitive_style", "learning_preference"],
        }
        # 需要过滤的非学习信息模式
        _name_patterns = [
            r"名叫\S+", r"叫\S+", r"我是\S+", r"名字是\S+",
            r"称呼\S+", r"叫我\S+", r"称呼我\S+",
        ]
        lines = []
        profile_dict = self._flatten_profile(profile)
        for label, keys in mapping.items():
            for key in keys:
                val = profile_dict.get(key, "").strip()
                if not val or val in ("未提及", "待补充", "未知"):
                    continue
                # 过滤掉人名等非学习信息
                for pat in _name_patterns:
                    val = re.sub(pat, "", val)
                val = val.strip(" ，,。.")
                if not val:
                    continue
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

    @staticmethod
    def _is_solve_request(message: str) -> bool:
        """检测是否为具体解题请求（应路由到 deep_solve），而非概念询问。

        必须同时满足：① 解题动作词 + ② 具体问题内容 + ③ 非纯概念询问。
        """
        import re
        text = message.strip()
        if len(text) < 6:
            return False

        # ① 解题动作词
        action_patterns = [
            r"[求解证明计算化简推导求证]+",   # 解、求、证明、计算...
            r"怎么[解做推算]",
            r"如何[解求]",
            r"(?:帮我|给我|帮忙)[解算](?:一下|这道|这个)?",
        ]
        has_action = any(re.search(p, text) for p in action_patterns)

        # ② 具体问题内容：包含数学符号、数字、公式结构
        content_patterns = [
            r"\b[fghxyzt]\s*\(.*\)\s*=",     # f(x)=
            r"\b[fghxyzt]\s*=",               # x=
            r"[=＝]\s*[?？]",                  # =?
            r"[＋＋\-+\-*/÷×^√∫∑∏]\s*\d",   # 运算符+数字
            r"\d+\s*[＋\-*/÷×]\s*\d+",       # 数字 运算符 数字
            r"已知.*[求证明计算]",
            r"[设若].*则.*[求证明]",
            r"这道题|这个题|这题|下列题目",
            r"解方?程|不等式|函数|极限|导数|积分|微分|矩阵|向量|概率",
            r"等于多少|结果是|答案是多少",
            r"[∠△⊥∥△⊙].*\d",              # 几何符号
            r"lim|sin|cos|tan|log|ln|dx|∫|∑|∏",
            r"\\frac|\\sqrt|\\int|\\sum|\\lim",
        ]
        has_content = any(re.search(p, text) for p in content_patterns)

        # ③ 排除纯概念询问（不是解题，是问定义）
        not_solve = [
            r"什么是|什么意思|是什么|的定义|的概念",
            r"为什么.*重要|为什么要学|有什么用|应用场景",
            r"讲讲|介绍一下|概述|总结一下|归纳",
            r"区别|对比|比较|异同|vs\b",
            r"学习方法|怎么学|如何入门|学习路线|推荐.*书|推荐.*课程",
            r"我不懂|不太明白|不理解.*概念|搞不懂.*意思",
        ]
        is_concept_question = any(re.search(p, text) for p in not_solve)

        return has_action and has_content and not is_concept_question

    def _try_deeptutor_reply(self, user_message: str, history: list, capability: str = "chat") -> str:
        from app.services.deeptutor_client import deeptutor_call, generate_visual_explanation, generate_video_script

        # ── 指定了非 chat 能力 → 直接路由，不走关键词检测 ──
        if capability != "chat":
            profile_context = self._build_profile_context_for_dt()
            return deeptutor_call(capability, user_message, history or [], profile_context)

        # Detect diagram/visualization requests
        vis_keywords = ["图解", "画图", "图示", "示意图", "流程图", "思维导图", "可视化",
                        "画个", "画一张", "用图", "图表", "图示说明", "图解释", "结构图"]
        if any(kw in user_message for kw in vis_keywords):
            return generate_visual_explanation(user_message)

        # Detect video script requests
        vid_script_kw = ["视频", "微课", "短片", "演示视频", "教学视频", "做个小视频",
                         "录个视频", "生成视频", "讲解视频", "可视化演示"]
        if any(kw in user_message for kw in vid_script_kw):
            return generate_video_script(user_message)

        # ── Build student profile context for DeepTutor ──
        profile_context = self._build_profile_context_for_dt()

        return deeptutor_call("chat", user_message, history or [], profile_context)

    def _build_profile_context_for_dt(self) -> str:
        """Build a concise student-profile summary for DeepTutor's memory_context.

        Uses the profile_facts stored during _run_intent() — these come directly
        from the orchestrator's state and reflect the latest conversation.
        """
        facts = getattr(self, "_current_profile_facts", {}) or {}
        if not facts:
            return ""

        label_map = {
            "background": "专业/年级",
            "target_course": "想学的课程",
            "knowledge_base": "已有基础",
            "weak_points": "薄弱点",
            "learning_goal": "学习目标",
            "time_budget": "时间安排",
            "preference": "学习偏好",
        }
        known_parts = []
        missing_parts = []
        for key, label in label_map.items():
            value = str(facts.get(key, "")).strip()
            if value and value not in ("未提及", "待补充", "未知", "", "无"):
                known_parts.append(f"{label}：{value}")
            else:
                missing_parts.append(label)

        if not known_parts:
            return ""

        ctx = "【学生画像】已知：" + "；".join(known_parts) + "。"
        if missing_parts:
            ctx += f"尚未了解：{'、'.join(missing_parts)}。"
        ctx += "请在对话中自然地融入你对学生的了解，不要复述这些信息。"
        return ctx

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

        valid_actions = {"diagnose", "plan", "resources", "profile", "knowledge", "none", "unsafe", "assess", "tutor"}
        if action not in valid_actions:
            action = "none"

        # 提取 facts
        facts_match = re.search(r'<facts>(.*?)</facts>', text, re.DOTALL)
        if facts_match:
            try:
                facts = json.loads(facts_match.group(1).strip())
            except json.JSONDecodeError:
                pass
            text = re.sub(r'<facts>.*?</facts>', '', text, flags=re.DOTALL)

        # 剥掉 proposal 和 execute 标签（内部标签，用户不可见）
        text = re.sub(r'<proposal>.*?</proposal>', '', text, flags=re.DOTALL)
        text = re.sub(r'<execute>.*?</execute>', '', text, flags=re.DOTALL)
        text = text.strip()

        return text, action, facts

    def _rule_fallback(self, message, context):
        """Conservative intent classifier -- default to 'none' (casual chat).

        ONLY triggers agent actions on unambiguous, explicit user requests.
        Single-character keyword matches (like "题") are deliberately avoided
        to prevent false positives from conversational words like "问题".
        """
        text = message.strip().lower()
        compact = re.sub(r"\s+", "", text)

        # ── Trivial / greeting ──────────────────────────────────────
        if text in EXACT_CASUAL or len(compact) <= 2:
            return self._fallback_result("none", "short_or_casual_message")

        # ── Confirmations (after system asked "要生成...吗？") ──────
        confirm_words = {"可以", "好的", "行", "嗯", "好", "ok", "yes", "对", "是的", "嗯嗯", "没错", "就这样", "按这个来"}
        if any(cw == compact or cw == text for cw in confirm_words):
            last_proposal = context.get("last_proposal")
            if last_proposal == "plan":
                return self._fallback_result("plan", "contextual_plan_confirmation")
            if last_proposal == "resources":
                return self._fallback_result("resources", "contextual_resource_confirmation")
            if last_proposal == "questions":
                return self._fallback_result("generate_questions", "contextual_question_confirmation")
            if last_proposal == "full":
                return self._fallback_result("plan,resources,generate_questions", "contextual_full_confirmation")
            if self._has_generation_confirmation_context(context):
                return self._fallback_result("plan,resources,generate_questions", "contextual_generation_confirmation")
            return self._fallback_result("none", "confirmation_without_generation_context", needs_clarification=True)

        # ── Mode-specific plan triggers (MUST run before generic _GEN_PLAN) ──
        # Priority: explicit mode keywords > subject-based hints > generic plan
        # This ensures ModePicker selections are correctly routed.

        # Explicit mode keywords (from ModePicker or user's explicit request)
        _EXPLICIT_FOCUS = [
            "帮我强化", "专项突破", "重点突破", "突击", "专攻",
            "针对性训练", "帮我补", "精进", "重点攻克",
        ]
        _EXPLICIT_DAILY = [
            "每日学习", "每天打卡", "每日计划", "日课", "每日打卡",
            "每天学", "天天练", "每日任务", "每日一练",
        ]
        _EXPLICIT_TEXTBOOK = [
            "系统学", "按章节", "从头学", "从基础开始",
            "完整学", "系统学习", "按教材",
        ]
        _EXPLICIT_PROJECT = [
            "做项目", "项目驱动", "项目实战", "做一个",
            "编程", "开发", "写一个", "搭建",
        ]
        # Subject-based hints (language/accumulation-type → daily is a good default)
        _SUBJECT_DAILY = [
            "英语", "日语", "韩语", "法语", "德语", "西语",
            "背单词", "学英语", "学日语",
        ]

        has_focus = any(p in compact for p in _EXPLICIT_FOCUS)
        has_daily = any(p in compact for p in _EXPLICIT_DAILY)
        has_textbook = any(p in compact for p in _EXPLICIT_TEXTBOOK)
        has_project = any(p in compact for p in _EXPLICIT_PROJECT)
        has_lang_subject = any(p in compact for p in _SUBJECT_DAILY)

        # Explicit mode keywords — these win over everything
        if has_focus:
            return self._fallback_result("plan", "focus_plan_request", plan_mode="focus")
        if has_project and not has_textbook:
            return self._fallback_result("plan", "project_path_request", plan_mode="textbook", path_mode="project")
        # Daily wins over textbook when both are explicit (user clicked 日课式 in ModePicker)
        if has_daily:
            return self._fallback_result("plan", "daily_path_request", plan_mode="textbook", path_mode="daily")
        if has_textbook:
            return self._fallback_result("plan", "textbook_plan_request", plan_mode="textbook")
        # Subject-based hint: language subjects default to daily (but only if no explicit mode)
        if has_lang_subject:
            return self._fallback_result("plan", "daily_path_request", plan_mode="textbook", path_mode="daily")

        # ── Explicit multi-word triggers only (no single-char matching) ──
        # NOTE: mode-specific checks above take priority; this catches generic plan
        # requests that don't match any specific mode.
        _GEN_PLAN = [
            "帮我规划", "帮我制定学习", "给我规划", "给我制定学习",
            "生成学习路径", "生成学习计划", "制定学习计划", "制定学习路径",
            "开始生成学习方案", "帮我生成学习方案", "就按这个生成",
            "生成吧", "开始吧", "按这些信息生成",
        ]
        if any(p in compact for p in _GEN_PLAN):
            # If course is known but no mode selected → route to planner anyway.
            # The orchestrator will show the mode picker directly, not via chat.
            profile_facts = context.get("profile_facts", {}) if isinstance(context.get("profile_facts"), dict) else {}
            course = str(profile_facts.get("target_course", ""))
            if course and not has_focus and not has_daily and not has_textbook and not has_project and not has_lang_subject:
                return self._fallback_result("plan", "explicit_generation_request")
            return self._fallback_result("plan", "explicit_generation_request")

        _GEN_FULL = ["完整方案", "全套方案", "全部方案", "整套方案", "生成全套", "全部生成"]
        if any(p in compact for p in _GEN_FULL):
            return self._fallback_result("full_workflow", "full_workflow_request")

        _GEN_QUESTION = [
            "出几道题", "出点题", "出些题", "给我出题", "帮我出题",
            "生成题目", "生成试题", "生成练习题", "生成几道题",
            "给我练习", "来几道题", "来点题", "来几道练习题",
            "做练习题", "做题练习", "出题给我", "给我出几道",
            "我想做题", "我想练习", "我想做几道", "我想练几道",
        ]
        if any(p in compact for p in _GEN_QUESTION):
            return self._fallback_result("generate_questions", "question_generation_request")

        _GRADE = ["帮我批改", "帮我判分", "帮我看看对不对", "帮我看下对不对"]
        if any(p in compact for p in _GRADE):
            return self._fallback_result("grade_answer", "grading_request")

        _RESOURCE = ["思维导图", "脑图", "生成资源", "给我资源", "给我资料"]
        if any(p in compact for p in _RESOURCE):
            return self._fallback_result("resources", "resource_request")

        _DIAG = ["帮我诊断", "分析薄弱点", "看看哪里薄弱", "我哪里差"]
        if any(p in compact for p in _DIAG):
            return self._fallback_result("diagnose", "diagnosis_request")

        # ── Combined assessment (批改+诊断+画像+规划+资源) ──
        _ASSESS = [
            "综合评估", "全面诊断", "综合诊断", "评估一下",
            "测一下水平", "测评", "学习评估", "效果评估",
        ]
        if any(p in compact for p in _ASSESS):
            return self._fallback_result("assess", "combined_assessment_request")

        # ── Problem solving: 具体解题请求 → deep_solve ──
        # 判定条件：包含解题动作词 + 具体问题内容（数字/公式/题目结构）
        if self._is_solve_request(user_message):
            return self._fallback_result("deep_tutor_chat", "solve_request", capability="deep_solve")

        # ── Intelligent tutoring (借力画像+诊断+资源的辅导) ──
        _TUTOR = [
            "给我讲讲", "帮我理解", "解释一下", "我不懂",
            "不太明白", "帮我分析一下", "教教我", "给我解释",
        ]
        if any(p in compact for p in _TUTOR):
            return self._fallback_result("tutor", "intelligent_tutoring_request")

        # ── Path adjustment triggers ──
        _ADJUST = [
            "调整路径", "调整计划", "修改路径", "修改计划", "改一下路径",
            "调整一下", "修改一下", "加快", "放慢", "多加点", "多加一些",
            "再加", "加一些练习", "多给点", "重新规划", "重新调整",
        ]
        if any(p in compact for p in _ADJUST):
            return self._fallback_result("plan", "path_adjustment", plan_mode="adjust")

        # ── Image generation triggers ──
        _GEN_IMAGE = [
            "生成一张图", "生成图片", "画一张", "画个图", "配图",
            "生成配图", "帮我画", "帮我生成图", "做张图",
        ]
        if any(p in compact for p in _GEN_IMAGE):
            return self._fallback_result("resources", "image_generation_request")

        # ── Video generation triggers ──
        _GEN_VIDEO = [
            "生成视频", "做个视频", "生成讲解视频", "教学视频",
            "微课视频", "动画讲解", "生成动画",
        ]
        if any(p in compact for p in _GEN_VIDEO):
            return self._fallback_result("resources", "video_generation_request")

        # ── Video / multimedia → handled by DeepTutor ──
        if any(w in text for w in ["视频", "动画", "微课", "短片"]):
            return self._fallback_result("none", "video_request")

        # ── Everything else → casual chat ──
        return self._fallback_result("none", "unclassified_fallback")


    def _fallback_result(self, action, reason, needs_clarification=False, plan_mode="", path_mode="", capability=""):
        result = {
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
        if plan_mode:
            result["plan_mode"] = plan_mode
        if path_mode:
            result["path_mode"] = path_mode
        if capability:
            result["capability"] = capability
        return result

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
