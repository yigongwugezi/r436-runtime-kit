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
你是学生唯一看到和对话的对象。你背后有多个子 Agent（画像分析、诊断、路径规划、资源生成、试题生成），但它们不直接对学生说话——所有回复由你统一出口。

## 对话原则
1. **自然口语化**：严禁"收到指令""已处理""请选择方向""画像完整度""当前画像信息如下"等机器话术
2. **不自动生成**：学生说"我想学XXX"只是表达意向。信息够了可以说"可以生成学习路径了，要开始吗？"，必须等学生确认
3. **引导性追问**：学生说模糊词时（"生成""方案""路径"），追问具体要什么
4. **精准执行**：学生明确指定了就只做那一件事，不多做。"出题"只出题、"资源"只资源
5. **分步引导**：首次按顺序逐一确认：路径(<proposal>plan</proposal>)→资源(<proposal>resources</proposal>)→练习题(<proposal>questions</proposal>)。已有就跳过
6. **增量优先**：修改现有内容时只调相关Agent，不重跑全量
7. **尊重拒绝**：学生说"不要"后不自动触发
8. **诚实**：没执行就不能说"已生成"

## 标签格式
- 确定学生要什么 → "好的，我来生成<execute>resources</execute>"
- 问学生要不要做什么 → "要生成路径吗？<proposal>plan</proposal>"
- 纯闲聊 → 不加标签

## 示例
学生："我想学微积分"
回复："好的！微积分是理工科核心课。你之前有接触过吗？每天大概能花多长时间？"

学生："零基础，每天三小时，一个月"
回复："明白了。已经可以生成学习路径了，要现在开始吗？<proposal>plan</proposal>"

学生："可以的"
回复："好的，马上帮你规划！"

路径生成后：
回复："路径已生成（5个阶段，30天）。要配套学习资源吗？<proposal>resources</proposal>"

## 禁止
- "请选择方向"
- "画像完整度 2/7"  
- "已生成"（除非真实执行了）
- 光说不练
- 说"帮你生成"但不加标签

## 画像标签
<facts>{...}</facts>
只包含学生明确说过的信息；课程名必须完整准确。"""

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

        needs_clarification = False

        # ── 规则先定确定性 action；只有兜不住时再让 LLM 猜。 ──
        rule_result = self._rule_fallback(user_message, context)
        rule_action = rule_result.get("action", "none")
        rule_reason = rule_result.get("reason", "")
        needs_clarification = rule_result.get("needs_clarification", False)
        action = rule_action
        deterministic_none = rule_action == "none" and rule_reason != "unclassified_fallback"

        if action == "none" and not deterministic_none and self.llm_client:
            for attempt in range(2):
                llm_action = self._llm_classify_action(user_message, context)
                if llm_action and llm_action != "full_workflow":
                    action = llm_action
                    break
                time.sleep(0.3)

        llm_reply = ""
        facts = {}
        llm_retry_count = 0

        # Auto-detect pending adjustment from grading
        pending_adj = context.get("profile_facts", {}).get("_pending_adjustment", "")
        if pending_adj and action == "none":
            et_labels = {"concept":"概念错误","calculation":"计算失误","misreading":"审题偏差","method":"方法不当","forgetting":"知识遗忘"}
            suggestion = f"上次练习中发现了{et_labels.get(pending_adj, pending_adj)}，建议调整学习计划重点强化这部分。要我现在帮你重新规划吗？"
            result = self._make_result(reply=suggestion, action="none", facts={})
            result["needs_clarification"] = False
            context["profile_facts"]["_pending_adjustment"] = ""
            return result

        if action in ("none", "tutoring", "") and not deterministic_none:
            dt = self._try_deeptutor_reply(user_message, self._history)
            if dt and len(dt) > 5:
                llm_reply = re.sub(r'<[^>]+>', '', dt).strip()

        if not llm_reply and not deterministic_none:
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

        # ── 第3步：LLM 失败时用极简兜底 ──
        if not llm_reply:
            llm_reply = self._action_reply_fallback(action, user_message, needs_clarification)

        self._save_history(user_message, llm_reply, context)

        result = self._make_result(reply=llm_reply, action=action, facts=facts)
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
            msgs.append({"role": "system", "content": f"当前学生状态：\n{ctx_text}"})
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
            valid = {"diagnose", "plan", "resources", "generate_questions", "grade_answer", "none"}
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

    def _try_deeptutor_reply(self, user_message: str, history: list) -> str:
        from app.services.deeptutor_client import deeptutor_call, generate_visual_explanation, generate_video_script
        try:
            from app.services.deeptutor_client import generate_manim_video
        except ImportError:
            generate_manim_video = None

        # Detect diagram/visualization requests
        vis_keywords = ["图解", "画图", "图示", "示意图", "流程图", "思维导图", "可视化",
                        "画个", "画一张", "用图", "图表", "图示说明", "图解释", "结构图"]
        if any(kw in user_message for kw in vis_keywords):
            return generate_visual_explanation(user_message)

        # Detect video/animation requests — render real mp4
        vid_keywords = ["生成.*动画", "做个.*动画", "动画演示", "演示动画", "教学动画"]
        if generate_manim_video and any(kw in user_message for kw in vid_keywords):
            result = generate_manim_video(user_message)
            if result:
                return f"已生成教学动画，文件路径：{result['path']}\n标题：{result['title']}\n你可以在资源库中查看。"

        # Detect video script requests
        vid_script_kw = ["视频", "微课", "短片", "演示视频", "教学视频", "做个小视频",
                         "录个视频", "生成视频", "讲解视频", "可视化演示"]
        if any(kw in user_message for kw in vid_script_kw):
            return generate_video_script(user_message)

        return deeptutor_call("chat", user_message, history or [])

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

        valid_actions = {"diagnose", "plan", "resources", "profile", "knowledge", "none", "unsafe"}
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
        text = message.strip().lower()
        compact = re.sub(r"\s+", "", text)
        confirm_words = {"可以", "好的", "行", "嗯", "好", "ok", "yes", "对", "是的", "嗯嗯", "没错", "就这样", "按这个来"}
        if text in EXACT_CASUAL or len(compact) <= 2:
            return self._fallback_result("none", "short_or_casual_message")

        # Mindmap check before explicit_generation
        if any(w in text for w in ["思维导图", "脑图"]):
            return self._fallback_result("resources", "mindmap_request")

        # Full workflow triggers
        if any(phrase in compact for phrase in ("完整方案","全套方案","全部方案","整套方案")):
            return self._fallback_result("full_workflow", "full_workflow_request")
        if "全套" in text and "方案" in text:
            return self._fallback_result("full_workflow", "full_workflow_request")
        if "完整" in text and "方案" in text:
            return self._fallback_result("full_workflow", "full_workflow_request")

        wants_profile = any(w in compact for w in ("学习画像", "画像", "评估基础", "分析基础"))
        wants_plan = any(w in compact for w in ("学习路径", "路径", "学习计划", "计划", "规划"))
        wants_resources = any(w in compact for w in ("学习资源", "资源", "资料", "练习"))
        if wants_profile and wants_plan and wants_resources:
            return self._fallback_result("full_workflow", "profile_plan_resource_request")

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
            return self._fallback_result("plan", "explicit_generation_request")

        if any(cw in compact for cw in confirm_words):
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

        if text in EXACT_CASUAL or len(compact) <= 2:
            return self._fallback_result("none", "short_or_casual_message")


            return self._fallback_result("resources", "mindmap_request")
        if any(w in text for w in ["出题", "做题", "测验", "考题", "题目", "题", "练习"]):
            return self._fallback_result("generate_questions", "question_generation_request")

        if any(w in text for w in ["批改", "判分", "帮我看看", "对不对", "检查下", "改了", "改卷"]):
            return self._fallback_result("grade_answer", "grading_request")

        if any(w in text for w in ["资源", "资料", "推荐"]):
            return self._fallback_result("resources", "resource_request")

        if any(w in text for w in ["路径", "规划", "计划", "安排", "怎么学", "该干什么", "下一步", "接下来"]):
            return self._fallback_result("plan", "planning_request")

        if any(w in text for w in ["薄弱", "诊断", "不会", "不懂", "哪里差"]):
            return self._fallback_result("diagnose", "diagnosis_request")

        if any(w in text for w in ["生成完整方案", "制定完整计划", "全部生成"]):
            return self._fallback_result("plan,resources,generate_questions", "explicit_full_request")
        if any(w in text for w in ["方案", "制定"]):
            return self._fallback_result("none", "ambiguous_generation_needs_clarification")

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
