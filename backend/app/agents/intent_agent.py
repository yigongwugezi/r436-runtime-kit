import json
import math
import re
from collections import Counter
from typing import Any, Literal

from app.agents.base import BaseAgent
from app.agents.intent_examples_zh import (
    INTENT_EXAMPLES_ZH,
    SEMANTIC_LABEL_SECONDARY,
    SEMANTIC_LABEL_TO_INTENT,
)
from app.agents.intent_routes import INTENT_ROUTES, ROUTE_AGENT_INTENTS


IntentType = Literal[
    "casual_chat",
    "date_query",
    "clarification",
    "info_request",
    "profile_query",
    "profile_update",
    "start_advice",
    "learning_plan",
    "tutoring",
    "resource_request",
    "progress_feedback",
    "project_help",
    "diagnosis",
    "full_workflow",
    "unsafe",
    "unknown",
]


class IntentAgent(BaseAgent):
    agent_id = "intent_agent"
    agent_name = "Intent Routing Agent"

    allowed_intents = set(INTENT_ROUTES) | {
        "general_chat",
        "review",
        "subject_create",
        "subject_select",
        "unknown",
    }
    canonical_primary_intents = {
        "full_workflow",
        "profile_update",
        "learning_plan",
        "resource_request",
        "diagnosis",
        "review",
        "subject_create",
        "subject_select",
        "general_chat",
        "unknown",
    }
    valid_task_types = {
        "profile_update",
        "diagnosis",
        "learning_plan",
        "learning_plan_revision",
        "resource_request",
        "review",
        "subject_create",
        "subject_select",
        "clarification",
        "general_chat",
    }

    exact_casual_patterns = {
        "你好",
        "您好",
        "hi",
        "hello",
        "在吗",
        "谢谢",
        "感谢",
        "好的",
        "好",
        "明白了",
        "知道了",
        "你是谁",
        "介绍一下",
    }

    high_risk_keywords = {"作弊", "代考", "代写", "破解", "攻击", "违法", "绕过检测"}

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        message = str(context.get("user_message", "")).strip()
        intent = self.classify(message, context=context)
        return {
            "intent": intent,
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "completed",
                "summary": f"Intent classified as {intent['intent']}.",
                "started_at": None,
                "finished_at": None,
            },
        }

    def classify(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context_data = self._normalize_context(context)
        rule_result = self._high_precision_rules(message)
        context_result = self._resolve_context_intent(message, context_data)
        semantic_result = self._route_by_semantic_examples(message)
        route_result = self._route_by_examples(message)
        llm_seed = semantic_result if semantic_result["confidence"] >= route_result["confidence"] else route_result

        llm_result = None
        if self._should_consult_llm(message, rule_result, llm_seed):
            llm_result = self._llm_classify(message, llm_seed)

        result = self._arbitrate_results(
            message=message,
            rule_result=rule_result,
            context_result=context_result,
            semantic_result=semantic_result,
            route_result=route_result,
            llm_result=llm_result,
        )
        finalized = self._finalize_result(result, message)
        return self._with_task_decomposition(finalized, message, context_data)

    def _high_precision_rules(self, message: str) -> dict[str, Any] | None:
        text = message.strip().lower()
        compact = "".join(text.split())

        if not compact:
            return self._result("casual_chat", 0.95, False, "用户输入为空或仅为空白。")

        if any(keyword in text for keyword in self.high_risk_keywords):
            return self._result("unsafe", 0.97, False, "命中高风险安全关键词。")

        if compact in self.exact_casual_patterns:
            return self._result("casual_chat", 0.97, False, "命中高置信寒暄表达。")

        if self._looks_vague(text):
            return self._result(
                "unknown",
                0.52,
                False,
                "The request is too vague to route safely without clarification.",
                source="rule_based_fallback",
                needs_clarification=True,
            )

        if self._looks_implicit_diagnosis(text):
            return self._result(
                "diagnosis",
                0.72,
                False,
                "The user implies confusion or a need to identify weak points.",
                secondary_intents=["learning_plan"],
            )

        if all(marker in text for marker in ("画像", "路径", "资源")):
            return self._result(
                "full_workflow",
                0.92,
                True,
                "The user asks for profile, learning path and resources in one request.",
                secondary_intents=["profile_update", "learning_plan", "resource_request"],
            )

        if any(marker in text for marker in ("练习和资料", "练习资料", "学习资料", "学习资源", "推荐资源", "给我一些")):
            return self._result(
                "resource_request",
                0.9,
                True,
                "The user asks for learning resources, practice or materials.",
            )

        if self.llm_client is not None and "操作系统" in text and any(marker in text for marker in ("想学", "学习")):
            return self._result(
                "learning_plan",
                0.86,
                True,
                "The user names a course topic and asks to learn it.",
                needs_subject=True,
            )

        utf8_plan_triggers = [
            "开始生成学习方案",
            "生成学习方案",
            "开始规划",
            "帮我规划",
            "制定学习计划",
            "生成学习路径",
            "开始生成",
            "先生成",
            "直接生成",
            "生成看看",
            "生成看一下",
            "看看效果",
            "不用在意准不准",
        ]
        if any(trigger in text for trigger in utf8_plan_triggers):
            return self._result("learning_plan", 0.95, True, "用户明确要求生成学习方案或学习路径。")

        date_patterns = [
            "今天是几号",
            "今天几号",
            "今天星期几",
            "今天日期",
            "现在几点",
            "现在时间",
            "今天是什么日子",
        ]
        if any(pattern in compact for pattern in date_patterns):
            return self._result("date_query", 0.96, False, "用户询问日期或时间，不写入学习画像。")

        # ── Full workflow: profile + path + resources ──
        if "画像" in text and "路径" in text and "资源" in text:
            return self._result("full_workflow", 0.92, True, "用户要求完整流程：画像构建+学习路径+资源生成。")

        # ── Profile-building request → profile_update ──
        if "构建学习画像" in text or "构建画像" in text:
            return self._result("profile_update", 0.90, False, "用户要求构建学习画像，属于画像更新。")
        # "帮我生成学习路径" should be learning_plan (already matched by plan_triggers below)

        # ── Resource request patterns ──
        resource_markers = ["找学习资源", "推荐资源", "生成资源", "找资源", "给我资源", "推荐一些", "推荐阅读", "拓展阅读"]
        if any(marker in text for marker in resource_markers):
            return self._result("resource_request", 0.92, True, "用户明确请求学习资源。")

        # ── Weakness diagnosis query ──
        if ("哪里" in text and "薄弱" in text) or ("哪里" in text and "不会" in text):
            return self._result("diagnosis", 0.85, False, "用户询问自身薄弱点，属于诊断类请求。")

        clarification_patterns = [
            "你啥意思",
            "你什么意思",
            "什么意思",
            "啥意思",
            "我没懂",
            "没看懂",
            "解释一下你刚才",
            "你刚才说的什么意思",
        ]
        if any(pattern in compact for pattern in clarification_patterns):
            return self._result("clarification", 0.92, False, "用户要求解释或澄清上一轮回复。")

        plan_triggers = [
            "开始生成学习方案",
            "生成学习方案",
            "开始规划",
            "帮我规划",
            "制定学习计划",
            "生成学习路径",
            "开始生成",
        ]
        if any(trigger in text for trigger in plan_triggers):
            return self._result("learning_plan", 0.95, True, "用户明确要求生成学习方案或学习路径。")

        time_only_pattern = (
            r"(?:我有|我想|希望|打算|计划|每天能学|每天学|每天)?"
            r"(?:\d+|一|两|二|三|四|五|六|七|八|九|十|半)\s*"
            r"(?:分钟|小时|天|周|星期|个月)"
            r"(?:时间|完成|学完|左右|以内|以上)?"
        )
        if re.fullmatch(time_only_pattern, compact):
            return self._result(
                "profile_update",
                0.9,
                False,
                "用户正在补充学习时间安排，属于画像更新。",
            )

        # ── Resource request high-precision triggers ──
        #   Must be BEFORE the compound rule so messages like
        #   "根据我的学习路径推荐资源" are not mistaken for full_workflow.
        resource_triggers = [
            "找学习资源",
            "推荐学习资源",
            "推荐资源",
            "给我推荐",
            "根据我的学习路径推荐",
            "给我找",
        ]
        if any(trigger in text for trigger in resource_triggers):
            return self._result(
                "resource_request",
                0.9,
                True,
                "用户明确请求查找或推荐学习资源。",
            )

        # ── Compound intent detection: user wants to BUILD multiple things ──
        #   Uses strict markers requiring action words (构建/生成/创建) + target.
        compound_groups = [
            {"构建画像", "生成画像", "构建学习画像", "生成学习画像"},        # profile_update (explicit build)
            {"生成学习路径", "构建学习路径", "制定学习计划", "生成学习方案", "帮我规划"},  # learning_plan (explicit build)
            {"生成学习资源", "构建学习资源", "生成资源", "创建资源"},        # resource_request (explicit build)
        ]
        matched_count = sum(
            1 for group in compound_groups if any(m in text for m in group)
        )
        if matched_count >= 2:
            return self._result(
                "full_workflow",
                0.88,
                True,
                "用户同时请求构建画像、路径规划和资源生成中的至少两项。",
            )

        # Fallback compound check: if the user mentions "画像、学习路径和学习资源"
        # in a single sentence (common full-workflow pattern), catch it.
        if "学习画像" in text and "学习路径" in text and "学习资源" in text:
            return self._result(
                "full_workflow",
                0.92,
                True,
                "用户同时提到学习画像、学习路径和学习资源，判定为全流程请求。",
            )

        # Clean UTF-8 rules for normal Chinese profile sentences. Keep this
        # before example routing so rich profile updates are never mistaken for
        # greetings or generic questions.
        utf8_profile_markers = [
            "我是",
            "本人是",
            "我的专业",
            "我基础",
            "我的基础",
            "我会",
            "我不会",
            "我不太会",
            "我想学",
            "我想学习",
            "想学习",
            "准备学",
            "复习",
            "为了考试",
            "为了项目",
            "为了竞赛",
            "希望",
            "喜欢",
            "不喜欢",
        ]
        utf8_detail_markers = [
            "基础",
            "薄弱",
            "比较弱",
            "一般",
            "还可以",
            "不会",
            "不熟",
            "考试",
            "项目",
            "入门",
            "小时",
            "分钟",
            "天",
            "周",
            "图解",
            "代码",
            "练习",
        ]
        if any(marker in text for marker in utf8_profile_markers) and any(
            marker in text for marker in utf8_detail_markers
        ):
            return self._result(
                "profile_update",
                0.92,
                False,
                "用户正在提供学习画像信息，先记录画像而不是直接生成方案。",
            )

        has_self_profile = any(marker in text for marker in ["我是", "我是一名", "本人是", "我的基础", "我基础"])
        has_learning_target = any(
            marker in text
            for marker in ["想学", "想学习", "我要学", "希望学", "准备学", "入门", "复习", "掌握", "了解"]
        )
        if has_self_profile and has_learning_target:
            return self._result(
                "learning_plan",
                0.88,
                True,
                "用户同时提供了个人背景和学习目标，适合启动画像构建与学习规划。",
            )

        # ── Interrogative diagnosis detection ──
        #   Catch "我哪里比较薄弱" / "我什么薄弱" / "我的薄弱点是什么" as
        #   profile_query (diagnosis inquiry) BEFORE the broad profile_update
        #   rule interprets "薄弱" as a detail marker.
        question_words = ["哪里", "什么", "哪", "吗", "怎么", "如何"]
        diagnosis_words = ["薄弱", "差", "不会", "不懂", "不好"]
        if any(q in text for q in question_words) and any(
            d in text for d in diagnosis_words
        ):
            return self._result(
                "profile_query",
                0.82,
                False,
                "用户以疑问句询问自身薄弱点或水平状态，判定为画像查询。",
            )

        profile_update_markers = [
            "我是",
            "我是一名",
            "本人是",
            "我的专业",
            "我是大一",
            "我是大二",
            "我是大三",
            "我是大四",
            "我基础",
            "我的基础",
            "我会",
            "我不会",
            "我喜欢",
            "我更喜欢",
            "我想学",
            "想学习",
            "想学",
            "想系统学习",
            "我要学",
            "希望学",
            "准备学",
            "考研",
            "复习",
            "画像",
            "构建画像",
            "构建学习画像",
        ]
        profile_detail_markers = [
            "基础",
            "薄弱",
            "比较弱",
            "一般",
            "还可以",
            "不会",
            "喜欢",
            "更喜欢",
            "不喜欢",
            "不要",
            "给我",
            "最好给",
            "每天能学",
            "能学",
            "完成",
            "小时",
            "分钟",
        ]
        if any(marker in text for marker in profile_update_markers) or any(
            marker in text for marker in profile_detail_markers
        ):
            return self._result(
                "profile_update",
                0.9,
                False,
                "用户正在补充画像字段，先记录信息并追问缺失项。",
            )

        fragments = [segment for segment in re.split(r"[，。,.!?！？；;、\s]+", text) if segment]
        has_grade = any(segment in {"大一", "大二", "大三", "大四", "研一", "研二", "研三"} for segment in fragments)
        has_major = any(
            any(hint in segment for hint in ["软件", "计算机", "人工智能", "电子", "信息", "自动化", "数学", "统计", "工程"])
            for segment in fragments
        )
        has_student_role = any(segment in {"学生", "本科生", "研究生", "大学生", "高职学生"} for segment in fragments)
        if has_major and (has_grade or has_student_role):
            return self._result(
                "profile_update",
                0.9,
                False,
                "用户用碎片化短语补充年级、专业或身份背景。",
            )

        return None

    def _normalize_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        normalized = dict(context)
        last_intent = normalized.get("last_intent")
        if isinstance(last_intent, dict):
            normalized["last_intent"] = last_intent.get("intent") or last_intent.get("primary_intent")
        last_result = normalized.get("last_agent_result") or normalized.get("last_result")
        if isinstance(last_result, dict):
            normalized.setdefault("has_learning_path", bool(last_result.get("learning_path")))
            normalized.setdefault("has_resources", bool(last_result.get("resources")))
            normalized.setdefault("has_diagnosis", bool(last_result.get("diagnosis")))
            normalized.setdefault("recent_resource_ids", self._resource_ids_from_result(last_result))
            normalized.setdefault("recent_weak_topics", self._weak_topics_from_result(last_result))
            normalized.setdefault("recent_stage_id", self._stage_id_from_result(last_result))
        return normalized

    def _resolve_context_intent(self, message: str, context: dict[str, Any]) -> dict[str, Any] | None:
        text = message.strip().lower()
        compact = "".join(text.split())
        if not compact:
            return None

        if self._is_continue_request(compact):
            if self._has_path_context(context):
                return self._context_result(
                    self._intent_from_last(context, default="learning_plan"),
                    0.82,
                    "继续当前学习路径或最近阶段。",
                    context,
                    extracted={"context_used": True, "plan_revision": "continue"},
                )
            return self._context_clarification("你想继续哪个科目或学习计划？")

        if self._is_next_step_request(compact):
            if self._has_diagnosis_context(context):
                return self._context_result(
                    "diagnosis",
                    0.82,
                    "根据最近诊断判断下一步补救动作。",
                    context,
                    secondary_intents=["learning_plan", "resource_request"],
                    extracted={"context_used": True, "plan_revision": "next_step"},
                )
            if self._has_path_context(context):
                return self._context_result(
                    "learning_plan",
                    0.8,
                    "根据已有学习路径安排下一步。",
                    context,
                    secondary_intents=["resource_request"],
                    extracted={"context_used": True, "plan_revision": "next_step"},
                )
            return self._context_clarification("你想让我基于哪个学习路径或诊断结果安排下一步？")

        if self._is_too_difficult_feedback(compact):
            if self._has_path_context(context) or self._has_resource_context(context):
                return self._context_result(
                    "diagnosis",
                    0.78,
                    "用户反馈当前阶段或资源过难，需要诊断并调整资源。",
                    context,
                    secondary_intents=["resource_request", "learning_plan"],
                    extracted={
                        "context_used": True,
                        "feedback": "too_difficult",
                        "difficulty_preference": "easier",
                    },
                )
            return self._context_result(
                "diagnosis",
                0.66,
                "用户表达学习内容过难，但缺少具体阶段或资源上下文。",
                context,
                secondary_intents=["learning_plan"],
                extracted={"context_used": False, "feedback": "too_difficult"},
            )

        if self._is_easier_request(compact):
            target_intent = self._simplify_target_intent(context)
            if target_intent:
                secondary = ["resource_request"] if target_intent == "learning_plan" and self._has_resource_context(context) else None
                return self._context_result(
                    target_intent,
                    0.84,
                    "用户基于当前上下文请求降低难度。",
                    context,
                    secondary_intents=secondary,
                    extracted={
                        "context_used": True,
                        "difficulty_preference": "easier",
                        "plan_revision": "simplify",
                    },
                )
            return self._context_clarification("你想把哪个学习计划或资源换得更简单一些？")

        if self._is_still_confused(compact):
            secondary = ["resource_request"]
            confidence = 0.78 if self._has_diagnosis_context(context) or self._has_path_context(context) else 0.68
            return self._context_result(
                "diagnosis",
                confidence,
                "用户表达仍然没有理解，需要重新诊断理解困难点。",
                context,
                secondary_intents=secondary,
                extracted={"context_used": bool(context), "feedback": "still_confused"},
            )

        if self._is_resource_reference(compact):
            if self._has_resource_context(context):
                return self._context_result(
                    "resource_request",
                    0.84,
                    "用户引用最近生成或查看过的资源。",
                    context,
                    extracted={"context_used": True, "resource_reference": "recent"},
                )
            return self._context_clarification("你说的是刚才哪一个资源？")

        if self._is_weak_topic_reference(compact):
            if self._has_diagnosis_context(context):
                return self._context_result(
                    "learning_plan",
                    0.84,
                    "用户要求基于刚才的薄弱点安排后续学习。",
                    context,
                    secondary_intents=["resource_request"],
                    extracted={"context_used": True, "plan_revision": "from_recent_weak_topic"},
                )
            return self._context_clarification("你想基于哪个薄弱点来安排学习？")

        if self._is_regenerate_request(compact):
            target_intent = self._intent_from_last(context)
            if "诊断" in text:
                target_intent = "diagnosis"
            if target_intent in {"learning_plan", "resource_request", "diagnosis"}:
                return self._context_result(
                    target_intent,
                    0.82,
                    "用户要求重新生成上一轮对应结果。",
                    context,
                    extracted={"context_used": True, "plan_revision": "regenerate"},
                )
            return self._context_clarification("你想重新生成学习路径、资源，还是诊断结果？")

        if self._is_change_one_request(compact):
            target_intent = self._intent_from_last(context)
            if target_intent in {"learning_plan", "resource_request", "diagnosis"}:
                return self._context_result(
                    target_intent,
                    0.8,
                    "用户要求替换上一轮对应结果。",
                    context,
                    extracted={"context_used": True, "plan_revision": "alternative"},
                )
            return self._context_clarification("你想换一个学习计划、资源，还是诊断结果？")

        if self._is_fewer_items_request(compact):
            target_intent = self._intent_from_last(context)
            if target_intent in {"learning_plan", "resource_request"}:
                return self._context_result(
                    target_intent,
                    0.8,
                    "用户要求减少上一轮输出数量。",
                    context,
                    extracted={"context_used": True, "constraint": "fewer_items"},
                )
            return self._context_clarification("你想让我减少学习计划阶段，还是减少资源数量？")

        if self._is_too_easy_feedback(compact):
            target_intent = self._intent_from_last(context, default="learning_plan")
            return self._context_result(
                target_intent if target_intent in {"learning_plan", "resource_request"} else "diagnosis",
                0.72,
                "用户反馈内容过于简单，需要调整难度或重新诊断。",
                context,
                secondary_intents=["learning_plan"],
                extracted={
                    "context_used": bool(context),
                    "feedback": "too_easy",
                    "difficulty_preference": "harder",
                },
            )

        if self._is_poor_explanation_feedback(compact):
            return self._context_result(
                "diagnosis",
                0.7,
                "用户反馈解释质量不好，需要诊断理解阻塞并换资源。",
                context,
                secondary_intents=["resource_request"],
                extracted={"context_used": bool(context), "feedback": "poor_explanation"},
            )

        return None

    def _context_result(
        self,
        intent: str,
        confidence: float,
        reason: str,
        context: dict[str, Any],
        *,
        secondary_intents: list[str] | None = None,
        extracted: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = {
            "context_used": bool(extracted or context),
            **(extracted or {}),
        }
        return self._result(
            intent,
            min(confidence, 0.95),
            intent in ROUTE_AGENT_INTENTS or intent == "diagnosis",
            f"Context-aware routing: {reason}",
            source="context_aware",
            secondary_intents=secondary_intents,
            extracted=data,
        )

    def _context_clarification(self, question: str) -> dict[str, Any]:
        return self._result(
            "unknown",
            0.42,
            False,
            "Context-aware routing needs clarification because the utterance depends on missing context.",
            source="context_aware",
            needs_clarification=True,
            clarification_question=question,
            extracted={"context_used": False},
        )

    def _intent_from_last(self, context: dict[str, Any], default: str = "unknown") -> str:
        intent = str(context.get("last_intent") or default)
        if intent == "full_workflow":
            return "learning_plan"
        return intent if intent in {"learning_plan", "resource_request", "diagnosis"} else default

    def _has_path_context(self, context: dict[str, Any]) -> bool:
        return bool(context.get("has_learning_path") or context.get("recent_stage_id"))

    def _has_resource_context(self, context: dict[str, Any]) -> bool:
        return bool(context.get("has_resources") or context.get("recent_resource_ids"))

    def _has_diagnosis_context(self, context: dict[str, Any]) -> bool:
        return bool(context.get("has_diagnosis") or context.get("recent_weak_topics"))

    def _has_adjustable_context(self, context: dict[str, Any]) -> bool:
        return bool(
            self._has_path_context(context)
            or self._has_resource_context(context)
            or self._has_diagnosis_context(context)
            or self._intent_from_last(context) != "unknown"
        )

    def _simplify_target_intent(self, context: dict[str, Any]) -> str | None:
        if not self._has_adjustable_context(context):
            return None

        last_intent = self._intent_from_last(context)
        if last_intent == "resource_request":
            return "resource_request"
        if last_intent in {"learning_plan", "diagnosis"}:
            return "learning_plan"
        if self._has_resource_context(context) and not self._has_path_context(context) and not self._has_diagnosis_context(context):
            return "resource_request"
        if self._has_path_context(context) or self._has_diagnosis_context(context):
            return "learning_plan"
        if self._has_resource_context(context):
            return "resource_request"
        return None

    def _resource_ids_from_result(self, result: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for item in result.get("resources") or []:
            if isinstance(item, dict):
                resource_id = item.get("id") or item.get("resource_id")
                if resource_id:
                    ids.append(str(resource_id))
        return ids

    def _weak_topics_from_result(self, result: dict[str, Any]) -> list[str]:
        diagnosis = result.get("diagnosis") if isinstance(result.get("diagnosis"), dict) else {}
        topics: list[str] = []
        for item in diagnosis.get("weak_topics") or diagnosis.get("weak_knowledge_points") or []:
            if isinstance(item, dict):
                topic = item.get("name") or item.get("topic") or item.get("title")
            else:
                topic = item
            if topic:
                topics.append(str(topic))
        return topics

    def _stage_id_from_result(self, result: dict[str, Any]) -> str | None:
        diagnosis = result.get("diagnosis") if isinstance(result.get("diagnosis"), dict) else {}
        if diagnosis.get("recommended_stage_id"):
            return str(diagnosis.get("recommended_stage_id"))
        stages = result.get("learning_path") or []
        if stages and isinstance(stages[0], dict):
            stage_id = stages[0].get("id") or stages[0].get("stage_id")
            return str(stage_id) if stage_id else None
        return None

    def _is_continue_request(self, compact: str) -> bool:
        return compact in {"继续", "继续吧", "接着", "接着来", "往下继续", "继续学习"}

    def _is_next_step_request(self, compact: str) -> bool:
        return compact in {"下一步", "下一步呢", "接下来", "然后呢", "后面呢", "接下来呢"}

    def _is_easier_request(self, compact: str) -> bool:
        return any(
            phrase in compact
            for phrase in (
                "换简单点",
                "简单一点",
                "简单点",
                "换个简单点的",
                "降低难度",
                "给我简单一点的",
                "不要这么难",
                "换成入门一点的",
                "容易点",
                "别太难",
                "换个简单",
            )
        )

    def _is_too_difficult_feedback(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("太难", "太复杂", "难懂", "看不懂", "跟不上"))

    def _is_still_confused(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("我还是不懂", "还是不懂", "不明白", "没懂", "听不懂"))

    def _is_resource_reference(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("那个资源", "刚才那个资源", "给我那个", "这个资源"))

    def _is_weak_topic_reference(self, compact: str) -> bool:
        return "刚才" in compact and any(word in compact for word in ("薄弱点", "弱点", "短板")) and any(
            word in compact for word in ("安排", "计划", "资源")
        )

    def _is_regenerate_request(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("重新生成", "重新来", "重来", "再生成", "重新诊断"))

    def _is_change_one_request(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("换一个", "换个", "另一个", "换一份", "换一版"))

    def _is_fewer_items_request(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("不要太多", "少一点", "少点", "精简一点", "简短点"))

    def _is_too_easy_feedback(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("太简单", "太容易", "不够难"))

    def _is_poor_explanation_feedback(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("讲得不好", "解释不好", "讲不清楚"))

    def _route_by_semantic_examples(self, message: str) -> dict[str, Any]:
        query_tokens = self._tokenize(message)
        if not query_tokens:
            result = self._result(
                "unknown",
                0.4,
                False,
                "输入缺少可用于语义路由的有效词元。",
                source="semantic_examples",
            )
            result["semantic_label"] = "empty"
            result["semantic_score"] = 0.0
            return result

        best_label = "unknown"
        best_example = ""
        best_score = 0.0

        for label, examples in INTENT_EXAMPLES_ZH.items():
            for example in examples:
                score = self._hybrid_similarity(query_tokens, message, example)
                if score > best_score:
                    best_label = label
                    best_example = example
                    best_score = score

        intent = SEMANTIC_LABEL_TO_INTENT.get(best_label, "unknown")
        confidence = self._semantic_score_to_confidence(best_score, best_label)
        secondary = list(SEMANTIC_LABEL_SECONDARY.get(best_label, []))
        needs_clarification = best_label == "ambiguous"
        clarification_question = None
        if needs_clarification:
            clarification_question = "你希望我先帮你做学习画像、规划路径、推荐资源，还是诊断薄弱点？"

        if best_score < 0.22:
            intent = "unknown"
            confidence = 0.38
            secondary = []
            best_label = "unknown"

        result = self._result(
            intent,
            confidence,
            intent in ROUTE_AGENT_INTENTS or intent == "diagnosis",
            f"语义样本路由匹配到 {best_label}：『{best_example}』，相似度 {best_score:.2f}。",
            source="semantic_examples",
            secondary_intents=secondary,
            needs_subject=best_label == "subject_create_or_learning_plan",
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
        )
        result["semantic_label"] = best_label
        result["semantic_score"] = best_score
        return result

    def _route_by_examples(self, message: str) -> dict[str, Any]:
        query_tokens = self._tokenize(message)
        if not query_tokens:
            return self._result("unknown", 0.4, False, "输入缺少可用于路由的有效词元。")

        best_intent = "unknown"
        best_score = 0.0
        best_example = ""

        for intent, route in INTENT_ROUTES.items():
            for example in route["examples"]:
                score = self._hybrid_similarity(query_tokens, message, example)
                if score > best_score:
                    best_score = score
                    best_intent = intent
                    best_example = example

        confidence = self._score_to_confidence(best_score)
        return self._result(
            best_intent,
            confidence,
            best_intent in ROUTE_AGENT_INTENTS,
            f"示例语义路由匹配到「{best_example}」，相似度 {best_score:.2f}。",
        )

    def _hybrid_similarity(self, query_tokens: list[str], message: str, example: str) -> float:
        example_tokens = self._tokenize(example)
        cosine = self._cosine(query_tokens, example_tokens)
        char_score = self._char_jaccard(message, example)
        phrase_bonus = 0.0
        if message.strip() in example or example in message.strip():
            phrase_bonus = 0.25
        return min(1.0, 0.55 * cosine + 0.35 * char_score + phrase_bonus)

    def _tokenize(self, text: str) -> list[str]:
        lowered = text.lower().strip()
        english = re.findall(r"[a-zA-Z][a-zA-Z0-9_+#-]*", lowered)
        chinese = re.findall(r"[\u4e00-\u9fff]", lowered)
        chinese_bigrams = [a + b for a, b in zip(chinese, chinese[1:])]
        return english + chinese + chinese_bigrams

    def _cosine(self, left: list[str], right: list[str]) -> float:
        if not left or not right:
            return 0.0
        left_counter = Counter(left)
        right_counter = Counter(right)
        shared = set(left_counter) & set(right_counter)
        numerator = sum(left_counter[token] * right_counter[token] for token in shared)
        left_norm = math.sqrt(sum(value * value for value in left_counter.values()))
        right_norm = math.sqrt(sum(value * value for value in right_counter.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _char_jaccard(self, left: str, right: str) -> float:
        left_chars = {char for char in left.lower() if not char.isspace()}
        right_chars = {char for char in right.lower() if not char.isspace()}
        if not left_chars or not right_chars:
            return 0.0
        return len(left_chars & right_chars) / len(left_chars | right_chars)

    def _score_to_confidence(self, score: float) -> float:
        if score >= 0.75:
            return 0.9
        if score >= 0.6:
            return 0.78
        if score >= 0.45:
            return 0.65
        return max(0.35, score)

    def _semantic_score_to_confidence(self, score: float, label: str) -> float:
        if score >= 0.88:
            return 0.94
        if score >= 0.72:
            return 0.86
        if score >= 0.58:
            return 0.76
        if score >= 0.44:
            return 0.64 if label != "ambiguous" else 0.58
        if score >= 0.30:
            return 0.52
        return max(0.35, score)

    def _should_consult_llm(
        self,
        message: str,
        rule_result: dict[str, Any] | None,
        route_result: dict[str, Any] | None,
    ) -> bool:
        if self.llm_client is None:
            return False
        text = message.strip()
        if not text:
            return False
        if (
            rule_result
            and rule_result.get("confidence", 0) >= 0.86
            and not self._has_multi_intent_signal(text)
            and not self._looks_implicit_diagnosis(text)
            and not self._looks_vague(text)
        ):
            return False
        if route_result is None:
            return True
        return (
            route_result.get("confidence", 0) < 0.78
            or self._has_multi_intent_signal(text)
            or self._looks_implicit_diagnosis(text)
            or self._looks_vague(text)
        )

    def _arbitrate_results(
        self,
        *,
        message: str,
        rule_result: dict[str, Any] | None,
        context_result: dict[str, Any] | None,
        semantic_result: dict[str, Any],
        route_result: dict[str, Any],
        llm_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        candidates = [
            candidate
            for candidate in (rule_result, context_result, semantic_result, route_result, llm_result)
            if candidate
        ]
        if not candidates:
            return self._result(
                "unknown",
                0.45,
                False,
                "Rule, semantic examples and model fallback could not classify the request reliably.",
                source="rule_based_fallback",
            )

        if (
            rule_result
            and rule_result.get("intent") in {"unsafe", "date_query", "clarification"}
            and float(rule_result.get("confidence", 0.0)) >= 0.9
        ):
            return dict(rule_result)

        if context_result and context_result.get("needs_clarification"):
            return self._merge_candidate_metadata(dict(context_result), candidates, message)

        if (
            context_result
            and context_result.get("source") == "context_aware"
            and float(context_result.get("confidence", 0.0)) >= 0.66
            and self._candidate_primary(context_result) != "unknown"
        ):
            return self._merge_candidate_metadata(dict(context_result), candidates, message)

        semantic_label = str(semantic_result.get("semantic_label", ""))
        if semantic_label in {"general_chat", "ambiguous", "off_topic"} and semantic_result["confidence"] >= 0.72:
            return self._merge_candidate_metadata(dict(semantic_result), candidates, message)

        # A real LLM JSON result is trusted when it agrees with the semantic router,
        # so existing tests can verify that the LLM path is still alive.
        if llm_result and llm_result.get("source") == "llm_generated":
            llm_primary = self._candidate_primary(llm_result)
            semantic_primary = self._candidate_primary(semantic_result)
            if llm_primary == semantic_primary or llm_result.get("confidence", 0) >= 0.82:
                return self._merge_candidate_metadata(dict(llm_result), candidates, message)

        chosen = max(candidates, key=lambda item: self._candidate_score(item, candidates, message))
        semantic_primary = self._candidate_primary(semantic_result)
        semantic_can_override = (
            (semantic_primary == "full_workflow" and self._has_full_workflow_signal(message))
            or (semantic_primary == "diagnosis" and self._has_diagnosis_signal(message))
            or (semantic_primary == "resource_request" and self._has_resource_signal(message))
            or (semantic_primary == "learning_plan" and bool(self._extract_subject_name(message)))
        )
        if (
            semantic_result.get("confidence", 0) >= 0.76
            and semantic_can_override
            and self._candidate_primary(chosen) in {"unknown", "profile_update"}
        ):
            chosen = semantic_result

        if (
            llm_result
            and self._candidate_primary(llm_result) == self._candidate_primary(semantic_result)
            and self._candidate_primary(llm_result) != "unknown"
            and float(llm_result.get("confidence", 0.0)) >= 0.68
        ):
            chosen = llm_result if llm_result.get("source") == "llm_generated" else semantic_result

        return self._merge_candidate_metadata(dict(chosen), candidates, message)

    def _candidate_score(
        self,
        result: dict[str, Any],
        candidates: list[dict[str, Any]],
        message: str,
    ) -> float:
        primary = self._candidate_primary(result)
        confidence = float(result.get("confidence", 0.0))
        score = confidence
        source = result.get("source")

        agreements = sum(1 for item in candidates if item is not result and self._candidate_primary(item) == primary)
        score += 0.04 * agreements

        if source == "semantic_examples":
            score += 0.04
        if source in {"llm_generated", "mock_llm"} and confidence >= 0.68:
            score += 0.03
        if primary == "unknown" and result.get("semantic_label") not in {"ambiguous", "off_topic"}:
            score -= 0.12
        if primary == "profile_update" and self._has_multi_intent_signal(message):
            score -= 0.08
        if primary == "full_workflow" and self._has_full_workflow_signal(message):
            score += 0.08
        if primary == "diagnosis" and (self._looks_implicit_diagnosis(message) or self._has_diagnosis_signal(message)):
            score += 0.08
        if primary == "resource_request" and self._has_resource_signal(message):
            score += 0.05
        return score

    def _merge_candidate_metadata(
        self,
        result: dict[str, Any],
        candidates: list[dict[str, Any]],
        message: str,
    ) -> dict[str, Any]:
        primary = self._candidate_primary(result)
        secondary: list[str] = []
        if result.get("source") == "context_aware":
            secondary = self._clean_secondary(result.get("secondary_intents", []))
        else:
            for candidate in candidates:
                candidate_primary = self._candidate_primary(candidate)
                if candidate_primary != primary:
                    legacy = self._legacy_intent(candidate_primary)
                    if legacy in self.allowed_intents and legacy not in {"unknown", "casual_chat"}:
                        secondary.append(legacy)
                secondary.extend(self._clean_secondary(candidate.get("secondary_intents", [])))
        result["secondary_intents"] = self._clean_secondary([*result.get("secondary_intents", []), *secondary])
        result["confidence"] = self._calibrate_confidence(result, candidates, message)

        if primary == "full_workflow":
            result["secondary_intents"] = self._clean_secondary(
                ["profile_update", "learning_plan", "resource_request", *result["secondary_intents"]]
            )
            result["should_run_agents"] = True
            result["should_run_full_workflow"] = True
        if primary == "diagnosis":
            result["should_run_agents"] = True
            if self._looks_implicit_diagnosis(message):
                result["reason"] = "Implicit diagnosis signal: the learner describes confusion or asks what to repair next."
        if primary == "general_chat":
            result["should_run_agents"] = False
            result["needs_clarification"] = False
            result["clarification_question"] = None
            result["secondary_intents"] = []
        if result.get("semantic_label") == "off_topic":
            result["should_run_agents"] = False
            result["needs_clarification"] = False
            result["clarification_question"] = None
            result["secondary_intents"] = []
        if result.get("semantic_label") == "ambiguous":
            result["needs_clarification"] = True
            result["should_run_agents"] = False
            result["secondary_intents"] = []
        if result.get("source") == "context_aware" and result.get("needs_clarification"):
            result["should_run_agents"] = False
            result["secondary_intents"] = []
        return result

    def _calibrate_confidence(
        self,
        result: dict[str, Any],
        candidates: list[dict[str, Any]],
        message: str,
    ) -> float:
        confidence = float(result.get("confidence", 0.0))
        primary = self._candidate_primary(result)
        agreements = sum(1 for item in candidates if item is not result and self._candidate_primary(item) == primary)
        conflicts = sum(
            1
            for item in candidates
            if self._candidate_primary(item) not in {primary, "unknown", "general_chat"}
        )

        confidence += min(0.08, agreements * 0.03)
        if conflicts >= 2 and agreements == 0:
            confidence -= 0.06
        if result.get("needs_clarification"):
            confidence = min(confidence, 0.6)
        if primary == "unknown":
            confidence = min(confidence, 0.55)
        if primary == "full_workflow" and self._has_full_workflow_signal(message):
            confidence = max(confidence, 0.8)
        if primary == "diagnosis" and self._has_diagnosis_signal(message):
            confidence = max(confidence, 0.78)
        if primary == "resource_request" and self._has_resource_signal(message):
            confidence = max(confidence, 0.72)
        return max(0.0, min(0.98, confidence))

    def _candidate_primary(self, result: dict[str, Any]) -> str:
        primary = str(result.get("primary_intent") or self._primary_from_legacy(str(result.get("intent", "unknown"))))
        return primary if primary in self.canonical_primary_intents else self._primary_from_legacy(primary)

    def _has_multi_intent_signal(self, message: str) -> bool:
        text = message.lower()
        signals = [
            ("画像" in text, "profile_update"),
            (any(word in text for word in ("路径", "计划", "方案", "规划")), "learning_plan"),
            (any(word in text for word in ("资源", "资料", "练习")), "resource_request"),
            (any(word in text for word in ("薄弱", "补哪里", "学得很乱", "不会")), "diagnosis"),
        ]
        return len({intent for matched, intent in signals if matched}) >= 2

    def _has_full_workflow_signal(self, message: str) -> bool:
        text = message.lower()
        has_profile = any(word in text for word in ("画像", "基础", "新生", "我是", "水平"))
        has_plan = any(word in text for word in ("路径", "计划", "方案", "规划", "路线"))
        has_resource = any(word in text for word in ("资源", "资料", "练习", "题"))
        return has_profile and has_plan and has_resource

    def _has_diagnosis_signal(self, message: str) -> bool:
        text = message.lower()
        return any(
            phrase in text
            for phrase in (
                "哪里比较薄弱",
                "薄弱点",
                "哪里不会",
                "补哪里",
                "学得很乱",
                "短板",
                "弱项",
                "差在哪里",
                "风险",
            )
        )

    def _has_resource_signal(self, message: str) -> bool:
        text = message.lower()
        return any(word in text for word in ("资源", "资料", "练习", "题", "quiz", "practice", "材料"))

    def _looks_implicit_diagnosis(self, message: str) -> bool:
        text = message.lower()
        return any(phrase in text for phrase in ("学得很乱", "不知道该补哪里", "该怎么补", "哪里没掌握", "跟不上"))

    def _looks_vague(self, message: str) -> bool:
        compact = "".join(message.lower().split())
        vague = {"帮我安排一下", "安排一下", "帮我看看", "怎么办", "给点建议", "帮我弄一下"}
        return compact in vague or (len(compact) <= 8 and any(item in compact for item in vague))

    def _llm_classify(self, message: str, route_result: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if self.llm_client is None:
            return None

        if self.llm_client.__class__.__name__ == "MockLLMClient":
            return self._mock_llm_classify(message, route_result)

        try:
            route_text = "\n".join(
                f"- {intent}: {route['description']}" for intent, route in INTENT_ROUTES.items()
            )
            content = self.llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are EduAgent's intent classifier. Return strict JSON only. "
                            "Do not return markdown or any text outside the JSON object."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Classify this user request for a course-learning workflow.\n"
                            f"Available legacy route intents:\n{route_text}\n\n"
                            "Return JSON with these keys: primary_intent, secondary_intents, "
                            "confidence, reason, should_run_full_workflow, needs_subject, "
                            "needs_clarification, clarification_question, extracted.\n"
                            "primary_intent must be one of: full_workflow, profile_update, "
                            "learning_plan, resource_request, diagnosis, review, subject_create, "
                            "subject_select, general_chat, unknown.\n"
                            "secondary_intents must be a list. extracted should contain "
                            "subject_name, time_budget, learning_goal, current_level, weak_topic, "
                            "requested_outputs.\n"
                            f"User message: {message}"
                        ),
                    },
                ],
                temperature=0,
                timeout=20,
            )
            parsed = self._load_json(content)
            primary = str(parsed.get("primary_intent") or parsed.get("intent") or "unknown")
            intent = self._legacy_intent(primary)
            confidence = float(parsed.get("confidence", 0.6))
            return self._result(
                intent,
                max(0.0, min(1.0, confidence)),
                bool(
                    parsed.get(
                        "should_run_agents",
                        parsed.get("should_run_full_workflow", intent in ROUTE_AGENT_INTENTS),
                    )
                ),
                str(parsed.get("reason", "LLM classified the user intent.")),
                source="llm_generated",
                primary_intent=primary,
                secondary_intents=self._clean_secondary(parsed.get("secondary_intents", [])),
                needs_subject=bool(parsed.get("needs_subject", False)),
                needs_clarification=bool(parsed.get("needs_clarification", False)),
                clarification_question=parsed.get("clarification_question"),
                extracted=parsed.get("extracted") if isinstance(parsed.get("extracted"), dict) else {},
            )
        except Exception:
            import logging
            logging.getLogger("app.agents.intent_agent").warning("LLM intent classification failed, returning None")
            return None

    def _mock_llm_classify(self, message: str, route_result: dict[str, Any] | None) -> dict[str, Any]:
        text = message.lower().strip()
        if self._looks_vague(text):
            return self._result(
                "unknown",
                0.52,
                False,
                "Mock LLM found the request too vague and asks for clarification.",
                source="mock_llm",
                needs_clarification=True,
                clarification_question="你希望我先帮你做学习画像、规划路径、推荐资源，还是诊断薄弱点？",
            )
        if self._looks_implicit_diagnosis(text):
            return self._result(
                "diagnosis",
                0.74,
                False,
                "Mock LLM recognized an implicit weakness diagnosis request.",
                source="mock_llm",
                secondary_intents=["learning_plan"],
            )
        if ("哪里" in text and "薄弱" in text) and any(word in text for word in ("资源", "资料", "接下来")):
            return self._result(
                "diagnosis",
                0.82,
                False,
                "Mock LLM recognized diagnosis with follow-up resource planning.",
                source="mock_llm",
                secondary_intents=["resource_request", "learning_plan"],
            )
        if self._has_multi_intent_signal(text):
            return self._result(
                "full_workflow",
                0.86,
                True,
                "Mock LLM recognized a multi-step profile, plan and resource request.",
                source="mock_llm",
                secondary_intents=["profile_update", "learning_plan", "resource_request"],
            )
        if "操作系统" in text and any(word in text for word in ("想学", "学习")):
            return self._result(
                "learning_plan",
                0.72,
                True,
                "Mock LLM recognized a new course learning-plan request.",
                source="mock_llm",
                needs_subject=True,
            )
        if route_result:
            result = dict(route_result)
            result["source"] = "mock_llm"
            result["reason"] = f"Mock LLM accepted rule/example route: {result.get('reason', '')}"
            return result
        return self._result("unknown", 0.45, False, "Mock LLM could not classify the request.", source="mock_llm")

    def _with_task_decomposition(
        self,
        result: dict[str, Any],
        message: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        decomposition = self._decompose_complex_utterance(message, context, result)
        if not decomposition:
            result.update(self._empty_decomposition())
            return result

        tasks = decomposition.get("tasks") or []
        constraints = decomposition.get("constraints") or {}
        execution_plan = [
            {
                "task_id": task.get("task_id"),
                "type": task.get("type"),
                "depends_on": task.get("depends_on", []),
            }
            for task in tasks
        ]
        result.update(
            {
                "tasks": tasks,
                "constraints": constraints,
                "execution_plan": execution_plan,
                "decomposition_source": decomposition.get("decomposition_source", "rule_based_decomposer"),
                "decomposition_confidence": decomposition.get("decomposition_confidence", 0.0),
            }
        )
        self._apply_decomposition_to_intent(result)
        return result

    def _empty_decomposition(self) -> dict[str, Any]:
        return {
            "tasks": [],
            "constraints": {},
            "execution_plan": [],
            "decomposition_source": "none",
            "decomposition_confidence": 0.0,
        }

    def _decompose_complex_utterance(
        self,
        message: str,
        context: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        text = message.strip()
        compact = "".join(text.lower().split())
        if not compact or result.get("primary_intent") == "general_chat" and not self._contains_learning_signal(text):
            return None
        if result.get("primary_intent") == "profile_update" and self._is_profile_preference_statement(text):
            return None
        if result.get("primary_intent") == "profile_update" and self._is_profile_fact_only(text):
            return None

        constraints = self._extract_p4_constraints(text, context, result)
        clauses = self._split_task_clauses(text)
        tasks: list[dict[str, Any]] = []

        for clause in clauses:
            for task_type in self._p4_task_types_from_clause(clause, context):
                if not task_type or task_type == "general_chat":
                    continue
                self._append_p4_task(tasks, task_type, clause, constraints)

        if not tasks:
            task_type = self._p4_task_type_from_clause(text, context)
            if task_type and task_type != "general_chat":
                self._append_p4_task(tasks, task_type, text, constraints)

        if not tasks and self._is_ambiguous_context_reference(compact):
            if self._has_adjustable_context(context):
                self._append_p4_task(tasks, "learning_plan_revision", text, constraints)
            else:
                self._append_p4_task(tasks, "clarification", text, constraints)
                constraints["clarification_reason"] = "missing_context_reference"

        if not tasks:
            return None

        tasks = self._dedupe_p4_tasks(tasks)
        if (
            len(tasks) == 1
            and not self._is_complex_expression(text)
            and result.get("primary_intent") in {"profile_update", "general_chat"}
        ):
            return None
        if len(tasks) == 1 and not self._is_complex_expression(text):
            return None

        self._wire_task_dependencies(tasks)
        confidence = self._decomposition_confidence(tasks, constraints, context)
        return {
            "tasks": tasks,
            "constraints": constraints,
            "decomposition_source": "context_aware_decomposer" if constraints.get("context_used") else "rule_based_decomposer",
            "decomposition_confidence": confidence,
        }

    def _split_task_clauses(self, text: str) -> list[str]:
        normalized = re.sub(r"(先|再|然后|接着|最后|顺便|另外|同时|并且|还有|而且)", r"，\1", text)
        parts = re.split(r"[，,。；;！？!?]+", normalized)
        return [part.strip(" ，。；;！？!?") for part in parts if part.strip(" ，。；;！？!?")]

    def _is_complex_expression(self, text: str) -> bool:
        return (
            len(self._split_task_clauses(text)) >= 2
            or "、" in text
            or self._has_multi_intent_signal(text)
            or self._has_full_workflow_signal(text)
            or any(
            marker in text
            for marker in ("先", "再", "然后", "最后", "顺便", "同时", "并且", "还有", "另外")
            )
        )

    def _contains_learning_signal(self, text: str) -> bool:
        return any(
            word in text
            for word in (
                "画像",
                "路径",
                "计划",
                "资源",
                "资料",
                "练习",
                "题",
                "诊断",
                "薄弱",
                "不会",
                "不懂",
                "补",
                "学习",
                "入门",
                "下一步",
                "怎么学",
            )
        )

    def _is_profile_fact_only(self, text: str) -> bool:
        has_profile_fact = any(
            word in text
            for word in (
                "我是",
                "我想学",
                "我想学习",
                "基础",
                "薄弱",
                "不会",
                "不熟",
                "喜欢",
                "时间",
                "为了",
                "更喜欢",
            )
        )
        has_action_request = any(
            word in text
            for word in (
                "帮我",
                "请",
                "给我",
                "推荐",
                "生成",
                "安排",
                "规划",
                "诊断",
                "下一步",
                "怎么学",
                "哪里",
                "先",
                "再",
                "然后",
                "最后",
            )
        )
        return has_profile_fact and not has_action_request

    def _is_profile_preference_statement(self, text: str) -> bool:
        has_preference = any(word in text for word in ("喜欢", "不喜欢", "更喜欢", "最好给我", "不要视频", "不想要视频", "别给视频"))
        has_explicit_generation = any(
            word in text
            for word in (
                "推荐资源",
                "推荐资料",
                "生成资源",
                "找资源",
                "给我资源",
                "给我资料",
                "给我文档",
                "给我练习",
                "安排",
                "诊断",
                "下一步",
                "怎么学",
                "先",
                "再",
                "然后",
                "最后",
            )
        )
        return has_preference and not has_explicit_generation

    def _p4_task_type_from_clause(self, clause: str, context: dict[str, Any]) -> str | None:
        task_types = self._p4_task_types_from_clause(clause, context)
        return task_types[0] if task_types else None

    def _p4_task_types_from_clause(self, clause: str, context: dict[str, Any]) -> list[str]:
        text = clause.strip().lower()
        compact = "".join(text.split())
        if not compact:
            return []
        if compact in self.exact_casual_patterns or compact in {"你好", "谢谢", "好的", "明白了"}:
            return ["general_chat"]
        if self._is_ambiguous_context_reference(compact) and not self._has_adjustable_context(context):
            return ["clarification"]
        if "刚才" in compact and "薄弱点" in compact and self._has_diagnosis_context(context):
            return []
        if self._is_weak_topic_reference(compact) and self._has_diagnosis_context(context):
            return ["learning_plan"]
        if "计划" in text and self._is_too_difficult_feedback(compact):
            return ["learning_plan_revision"]
        task_types: list[str] = []
        if self._looks_profile_task(text):
            task_types.append("profile_update")
        if self._looks_plan_revision_task(text, context):
            task_types.append("learning_plan_revision")
        elif self._looks_plan_task(text):
            task_types.append("learning_plan")
        if self._looks_diagnosis_task(text):
            task_types.append("diagnosis")
        if self._looks_resource_task(text):
            task_types.append("resource_request")
        if self._looks_review_task(text):
            task_types.append("review")
        return [item for item in dict.fromkeys(task_types) if item in self.valid_task_types]

    def _looks_profile_task(self, text: str) -> bool:
        return any(word in text for word in ("画像", "建画像", "学习画像", "评估我的基础", "更新我的水平"))

    def _looks_diagnosis_task(self, text: str) -> bool:
        return any(
            word in text
            for word in (
                "诊断",
                "哪里不会",
                "哪里薄弱",
                "薄弱点",
                "薄弱",
                "短板",
                "不会",
                "不懂",
                "没懂",
                "不牢",
                "不扎实",
                "不稳",
                "哪些知识点",
                "学得不好",
                "学不好",
                "补哪里",
                "太难",
            )
        )

    def _looks_resource_task(self, text: str) -> bool:
        return any(word in text for word in ("资源", "资料", "练习", "练习题", "题", "文档", "视频", "材料", "例题"))

    def _looks_plan_task(self, text: str) -> bool:
        if self._looks_resource_task(text) and any(word in text for word in ("路径对应", "根据路径", "根据我的学习路径", "对应的资源")):
            return False
        return any(word in text for word in ("路径", "路线", "计划", "规划", "安排", "下一步", "怎么学", "后面怎么", "学习方案"))

    def _looks_plan_revision_task(self, text: str, context: dict[str, Any]) -> bool:
        compact = "".join(text.split())
        if self._is_fewer_items_request(compact) and not any(word in text for word in ("计划", "路径", "安排", "阶段")):
            return False
        has_revision = any(
            word in text
            for word in (
                "改一下",
                "调整",
                "换简单",
                "简单一点",
                "降低难度",
                "不要太多",
                "别安排太多",
                "减少一点",
                "重新生成",
                "重来",
                "换一个",
                "换一版",
                "别像上次那么难",
            )
        )
        has_plan = any(word in text for word in ("计划", "路径", "安排", "后面", "明天", "刚才", "那个"))
        return has_revision and (has_plan or self._has_adjustable_context(context))

    def _looks_review_task(self, text: str) -> bool:
        return any(word in text for word in ("检查一下", "审核", "质量", "靠谱吗", "有没有问题"))

    def _is_ambiguous_context_reference(self, compact: str) -> bool:
        return any(phrase in compact for phrase in ("按那个来", "按刚才那个", "刚才那个", "像上次"))

    def _append_p4_task(
        self,
        tasks: list[dict[str, Any]],
        task_type: str,
        clause: str,
        constraints: dict[str, Any],
    ) -> None:
        if task_type not in self.valid_task_types:
            return
        task_id = f"task_{len(tasks) + 1}"
        task = {
            "task_id": task_id,
            "type": task_type,
            "reason": self._p4_task_reason(task_type, clause),
            "priority": len(tasks) + 1,
            "depends_on": [],
        }
        topic = self._extract_task_topic(clause) or constraints.get("target")
        if topic:
            task["target"] = topic
            if task_type in {"diagnosis", "resource_request", "learning_plan_revision"}:
                task["knowledge_points"] = [topic]
        if task_type == "resource_request":
            if constraints.get("resource_type"):
                task["resource_type"] = constraints["resource_type"]
            if constraints.get("exclude_resource_types"):
                task["exclude_resource_types"] = constraints["exclude_resource_types"]
        if task_type == "learning_plan_revision" and constraints.get("plan_revision"):
            task["revision_type"] = constraints["plan_revision"]
        tasks.append(task)

    def _p4_task_reason(self, task_type: str, clause: str) -> str:
        reasons = {
            "profile_update": "用户要求先建立或更新学习画像。",
            "diagnosis": "用户表达不会、不懂或要求定位薄弱点。",
            "learning_plan": "用户要求安排后续学习步骤或学习路径。",
            "learning_plan_revision": "用户要求调整已有计划或降低难度。",
            "resource_request": "用户要求推荐资料、练习或可执行资源。",
            "review": "用户要求检查输出质量或可信度。",
            "subject_create": "用户提出新的学习科目。",
            "subject_select": "用户选择已有学习科目。",
            "clarification": "用户引用了上下文对象，但当前会话缺少可解析上下文。",
            "general_chat": "用户进行普通寒暄。",
        }
        return f"{reasons.get(task_type, '用户请求可拆分为独立任务。')} 原句片段：{clause.strip()}"

    def _dedupe_p4_tasks(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for task in tasks:
            key = (str(task.get("type")), str(task.get("target", "")))
            if key in seen and task.get("type") not in {"resource_request"}:
                continue
            seen.add(key)
            task = dict(task)
            task["task_id"] = f"task_{len(deduped) + 1}"
            task["priority"] = len(deduped) + 1
            deduped.append(task)
        return deduped

    def _wire_task_dependencies(self, tasks: list[dict[str, Any]]) -> None:
        previous_actionable: list[str] = []
        for task in tasks:
            task_type = task.get("type")
            if task_type in {"resource_request", "learning_plan_revision", "review"} and previous_actionable:
                task["depends_on"] = [previous_actionable[-1]]
            elif task_type == "clarification":
                task["depends_on"] = []
            else:
                task["depends_on"] = []
            if task_type not in {"clarification", "general_chat"}:
                previous_actionable.append(str(task.get("task_id")))

    def _extract_p4_constraints(
        self,
        text: str,
        context: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        constraints: dict[str, Any] = {}
        compact = "".join(text.lower().split())
        if self._is_easier_request(compact) or "入门" in text or "不要太难" in text or "别像上次那么难" in text:
            constraints["difficulty_preference"] = "easier"
        if self._is_too_easy_feedback(compact):
            constraints["difficulty_preference"] = "harder"
        if self._is_too_difficult_feedback(compact) or "别像上次那么难" in text:
            constraints["feedback"] = "too_difficult"
            constraints.setdefault("difficulty_preference", "easier")
        if self._is_still_confused(compact):
            constraints["feedback"] = "still_confused"
        if self._is_fewer_items_request(compact) or any(word in text for word in ("数量别太多", "别安排太多", "别太多", "不要太多")):
            constraints["amount"] = "fewer_items"
            constraints["constraint"] = "fewer_items"
        if any(word in text for word in ("马上做", "立刻做", "现在就能做", "马上练")):
            constraints["immediacy"] = "quick_start"
        if "明天" in text:
            constraints["time_scope"] = "tomorrow"
        if any(word in text for word in ("重新生成", "重来", "重新来", "再生成")):
            constraints["plan_revision"] = "regenerate"
        elif self._is_easier_request(compact) or "别像上次那么难" in text:
            constraints["plan_revision"] = "simplify"
        elif self._is_change_one_request(compact):
            constraints["plan_revision"] = "alternative"

        resource_types: list[str] = []
        if any(word in text for word in ("文档", "文字资料", "文章")):
            resource_types.append("document")
        if any(word in text for word in ("练习", "练习题", "题", "实操")):
            resource_types.append("practice")
        if "视频" in text and not any(word in text for word in ("不要视频", "不想要视频", "别给视频")):
            resource_types.append("video")
        if resource_types:
            constraints["resource_type"] = list(dict.fromkeys(resource_types))
        if any(word in text for word in ("不要视频", "不想要视频", "别给视频", "不用视频")):
            constraints["exclude_resource_types"] = ["video"]

        target = self._extract_task_topic(text)
        weak_topics = context.get("recent_weak_topics") if isinstance(context, dict) else None
        if not target and isinstance(weak_topics, list) and weak_topics and any(word in text for word in ("刚才", "那个薄弱点", "按那个")):
            target = str(weak_topics[0])
            constraints["context_used"] = True
        if target:
            constraints["target"] = target
        if result.get("extracted", {}).get("subject_name"):
            constraints.setdefault("subject_name", result["extracted"]["subject_name"])
        if self._has_adjustable_context(context) and any(word in text for word in ("刚才", "那个", "上次", "继续", "下一步", "换", "重新")):
            constraints["context_used"] = True
        return constraints

    def _extract_task_topic(self, text: str) -> str | None:
        patterns = [
            r"给我\s*([^，。；;！？!?]{1,24}?)(?:的)?(?:练习题|练习|题|资料|资源|文档)",
            r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{1,12})(?:还是)?不懂",
            r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{1,12})学得不好",
            r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{1,12})(?:不会|不熟)",
            r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{1,12})(?:的)?(?:练习题|练习|题)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            topic = match.group(1).strip(" ，。；;！？!?的")
            if any(fragment in topic for fragment in ("换一个", "换个", "简单点", "简单一点")):
                continue
            topic = re.sub(r"^(我|最近|刚才|那个|那个薄弱点|一些|几个|简单|适合|现在阶段的)", "", topic)
            topic = re.sub(r"(简单一点|简单|数量别太多|不要太多|最好是能马上做的)$", "", topic).strip()
            subject = self._clean_subject_name(topic)
            if subject:
                return subject
        return None

    def _decomposition_confidence(
        self,
        tasks: list[dict[str, Any]],
        constraints: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        if tasks and tasks[0].get("type") == "clarification":
            return 0.5
        base = 0.78
        if len(tasks) >= 2:
            base += 0.07
        if constraints:
            base += 0.04
        if constraints.get("context_used") or self._has_adjustable_context(context):
            base += 0.03
        return round(min(0.92, base), 2)

    def _apply_decomposition_to_intent(self, result: dict[str, Any]) -> None:
        tasks = result.get("tasks") or []
        if not tasks:
            return
        if tasks[0].get("type") == "clarification":
            result.update(
                {
                    "intent": "unknown",
                    "primary_intent": "unknown",
                    "secondary_intents": [],
                    "should_run_agents": False,
                    "should_run_full_workflow": False,
                    "needs_clarification": True,
                    "clarification_question": result.get("clarification_question")
                    or "你想基于刚才哪个学习计划、资源或诊断结果来调整？",
                    "confidence": min(float(result.get("confidence", 0.0)), 0.58),
                }
            )
            return

        task_types = [str(task.get("type")) for task in tasks if task.get("type") in self.valid_task_types]
        workflow_core = {"profile_update", "learning_plan", "resource_request"}
        has_full_workflow = workflow_core.issubset(set(task_types)) and not any(
            task_type in task_types for task_type in ("diagnosis", "learning_plan_revision")
        )
        if has_full_workflow:
            primary = "full_workflow"
            intent = "full_workflow"
        else:
            primary = self._primary_from_task_type(task_types[0])
            intent = self._legacy_intent(primary)

        secondary = [] if len(tasks) > 1 else list(result.get("secondary_intents") or [])
        for task_type in task_types:
            mapped = self._primary_from_task_type(task_type)
            if mapped != primary and mapped != "general_chat" and mapped not in secondary:
                secondary.append(mapped)
        if primary == "diagnosis" and "resource_request" in task_types and "resource_request" not in secondary:
            secondary.append("resource_request")

        extracted = dict(result.get("extracted") or {})
        constraints = result.get("constraints") if isinstance(result.get("constraints"), dict) else {}
        for key in (
            "difficulty_preference",
            "feedback",
            "plan_revision",
            "constraint",
            "context_used",
            "resource_type",
            "exclude_resource_types",
        ):
            if constraints.get(key) not in (None, "", []):
                extracted[key] = constraints[key]
        if constraints.get("target") and not extracted.get("weak_topic"):
            extracted["weak_topic"] = constraints["target"]

        result.update(
            {
                "intent": intent,
                "primary_intent": primary,
                "secondary_intents": self._clean_secondary(secondary),
                "should_run_agents": intent in ROUTE_AGENT_INTENTS or intent == "diagnosis",
                "should_run_full_workflow": primary == "full_workflow",
                "needs_clarification": False,
                "clarification_question": None,
                "confidence": max(
                    float(result.get("confidence", 0.0)),
                    float(result.get("decomposition_confidence", 0.0)),
                ),
                "extracted": extracted,
                "reason": f"{result.get('reason', '')} Complex utterance decomposed into {len(tasks)} task(s).".strip(),
            }
        )

    def _primary_from_task_type(self, task_type: str) -> str:
        if task_type == "learning_plan_revision":
            return "learning_plan"
        if task_type == "clarification":
            return "unknown"
        if task_type in self.canonical_primary_intents:
            return task_type
        return "unknown"

    def _load_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            raise ValueError("Intent LLM response does not contain JSON.")
        return json.loads(text[start:end])

    def _result(
        self,
        intent: str,
        confidence: float,
        should_run_agents: bool,
        reason: str,
        *,
        source: str = "rule_based",
        primary_intent: str | None = None,
        secondary_intents: list[str] | None = None,
        needs_subject: bool = False,
        needs_clarification: bool = False,
        clarification_question: str | None = None,
        extracted: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if intent not in self.allowed_intents:
            intent = "unknown"
        return {
            "intent": intent,
            "primary_intent": primary_intent or self._primary_from_legacy(intent),
            "secondary_intents": secondary_intents or [],
            "confidence": confidence,
            "should_run_agents": should_run_agents,
            "should_run_full_workflow": intent == "full_workflow",
            "needs_subject": needs_subject,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "extracted": extracted or {},
            "reason": reason,
            "source": source,
        }

    def _finalize_result(self, result: dict[str, Any], message: str) -> dict[str, Any]:
        intent = self._legacy_intent(str(result.get("intent") or result.get("primary_intent") or "unknown"))
        primary = str(result.get("primary_intent") or self._primary_from_legacy(intent))
        if primary not in self.canonical_primary_intents:
            primary = self._primary_from_legacy(intent)

        extracted = self._merge_extracted(message, result.get("extracted"))
        secondary = self._clean_secondary(result.get("secondary_intents", []))
        if not secondary and result.get("source") != "context_aware":
            secondary = self._infer_secondary_intents(message, intent)
        secondary = [item for item in secondary if item != intent]

        is_general_chat = primary == "general_chat" or intent == "casual_chat"
        is_off_topic = result.get("semantic_label") == "off_topic"
        needs_clarification = (
            bool(result.get("needs_clarification"))
            or (self._looks_vague(message) and not is_general_chat)
            or (intent == "unknown" and not is_off_topic)
        )
        clarification_question = result.get("clarification_question")
        if needs_clarification and not clarification_question:
            clarification_question = "你希望我先帮你做学习画像、规划路径、推荐资源，还是诊断薄弱点？"
        if is_general_chat or is_off_topic:
            needs_clarification = False
            clarification_question = None

        needs_subject = bool(result.get("needs_subject")) or bool(
            extracted.get("subject_name") and intent in {"learning_plan", "subject_create"}
        )

        result.update(
            {
                "intent": intent,
                "primary_intent": primary,
                "secondary_intents": secondary,
                "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.0)))),
                "should_run_agents": bool(result.get("should_run_agents"))
                or intent in ROUTE_AGENT_INTENTS
                or intent == "diagnosis",
                "should_run_full_workflow": primary == "full_workflow" or intent == "full_workflow",
                "needs_subject": needs_subject,
                "needs_clarification": needs_clarification,
                "clarification_question": clarification_question,
                "extracted": extracted,
                "source": result.get("source") or "rule_based",
            }
        )
        return result

    def _legacy_intent(self, primary: str) -> str:
        if primary == "general_chat":
            return "casual_chat"
        if primary in {"subject_create", "subject_select"}:
            return "learning_plan"
        if primary in self.allowed_intents:
            return primary
        return "unknown"

    def _primary_from_legacy(self, intent: str) -> str:
        if intent == "casual_chat":
            return "general_chat"
        if intent in self.canonical_primary_intents:
            return intent
        return intent if intent in self.allowed_intents else "unknown"

    def _clean_secondary(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        allowed_secondary = {
            "full_workflow",
            "profile_update",
            "learning_plan",
            "resource_request",
            "diagnosis",
            "review",
            "subject_create",
            "subject_select",
        }
        cleaned: list[str] = []
        for item in value:
            intent = str(item)
            if intent == "general_chat":
                intent = "casual_chat"
            if intent in allowed_secondary and intent not in cleaned and intent != "unknown":
                cleaned.append(intent)
        return cleaned

    def _infer_secondary_intents(self, message: str, primary: str) -> list[str]:
        text = message.lower()
        candidates: list[str] = []
        if "画像" in text:
            candidates.append("profile_update")
        if any(word in text for word in ("路径", "计划", "方案", "规划", "接下来")):
            candidates.append("learning_plan")
        if any(word in text for word in ("资源", "资料", "练习", "题")):
            candidates.append("resource_request")
        if any(word in text for word in ("薄弱", "补哪里", "学得很乱", "不会", "诊断")):
            candidates.append("diagnosis")
        if primary == "full_workflow":
            candidates = ["profile_update", "learning_plan", "resource_request", *candidates]
        return [item for item in dict.fromkeys(candidates) if item != primary and item in self.allowed_intents]

    def _merge_extracted(self, message: str, existing: Any) -> dict[str, Any]:
        extracted = {
            "subject_name": None,
            "time_budget": None,
            "learning_goal": None,
            "current_level": None,
            "weak_topic": None,
            "requested_outputs": [],
            "difficulty_preference": None,
            "feedback": None,
            "resource_reference": None,
            "plan_revision": None,
            "constraint": None,
            "context_used": False,
        }
        if isinstance(existing, dict):
            for key in extracted:
                value = existing.get(key)
                if value not in (None, ""):
                    extracted[key] = value
        heuristic = self._extract_entities(message)
        for key, value in heuristic.items():
            if key == "requested_outputs" and value:
                extracted[key] = list(dict.fromkeys([*(extracted.get(key) or []), *value]))
            elif value and not extracted.get(key):
                extracted[key] = value
        return extracted

    def _extract_subject_name(self, text: str) -> str | None:
        patterns = [
            r"(?:\d+\s*天|[一二两三四五六七八九十]+\s*天|\d+\s*周|[一二两三四五六七八九十]+\s*周)\s*(?:入门|学会|掌握)\s*([A-Za-z0-9+#]+|[\u4e00-\u9fff]{2,12})",
            r"(?:我想|想|准备|开始|帮我|请帮我)?\s*(?:系统学习|学习|学|入门|复习)\s*([A-Za-z0-9+#]+|[\u4e00-\u9fff]{2,12})",
            r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{2,12})\s*(?:基础比较弱|基础弱|零基础|入门)",
        ]
        stop_words = {
            "一些",
            "一下",
            "学习",
            "路径",
            "计划",
            "方案",
            "资源",
            "资料",
            "练习",
            "画像",
            "阶段",
            "现在",
            "系统",
        }
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            subject = self._clean_subject_name(match.group(1))
            if subject and subject not in stop_words:
                return subject
        return None

    def _clean_subject_name(self, value: str) -> str | None:
        subject = value.strip(" ，。！？,.、")
        subject = re.split(r"(?:请|帮我|给我|需要|包括|构建|生成|制定|推荐|安排|怎么|如何|和|并|再|，|。|、|！|？|,|\\.)", subject)[0]
        subject = subject.strip(" ，。！？,.、")
        blocked_fragments = ("什么", "哪里", "资源", "资料", "练习", "得很", "该", "现在", "阶段")
        if subject.startswith("得") or any(fragment in subject for fragment in blocked_fragments):
            return None
        for suffix in ("基础比较弱", "基础弱", "基础", "入门"):
            if subject.endswith(suffix) and len(subject) > len(suffix):
                subject = subject[: -len(suffix)].strip()
        if not subject or len(subject) > 20:
            return None
        return subject

    def _extract_entities(self, message: str) -> dict[str, Any]:
        text = message.strip()
        result: dict[str, Any] = {"requested_outputs": []}

        subject = self._extract_subject_name(text)
        if subject:
            result["subject_name"] = subject

        time_match = re.search(r"(\d+\s*(?:天|周|小时|分钟|个月)|[一二两三四五六七八九十]+(?:天|周|小时|分钟|个月))", text)
        if time_match:
            result["time_budget"] = time_match.group(1)

        if any(word in text for word in ("新生", "零基础", "基础弱", "基础比较弱", "入门")):
            result["current_level"] = "beginner_or_weak_foundation"

        weak_match = re.search(r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{2,12})\s*基础(?:比较)?(?:薄弱|弱)", text)
        if weak_match is None:
            weak_match = re.search(r"([A-Za-z0-9+#]+|[\u4e00-\u9fff]{2,12})(?:不会|不熟)", text)
        if weak_match:
            weak_topic = weak_match.group(1)
            if "哪里" not in weak_topic:
                result["weak_topic"] = weak_topic

        if "画像" in text:
            result["requested_outputs"].append("profile")
        if any(word in text for word in ("路径", "计划", "方案", "规划")):
            result["requested_outputs"].append("learning_path")
        if any(word in text for word in ("资源", "资料", "练习")):
            result["requested_outputs"].append("resources")
        if any(word in text for word in ("薄弱", "诊断", "补哪里")):
            result["requested_outputs"].append("diagnosis")
        if result.get("subject_name"):
            result["learning_goal"] = f"学习{result['subject_name']}"
        return result
