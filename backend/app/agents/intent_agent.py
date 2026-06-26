import json
import math
import re
from collections import Counter
from typing import Any, Literal

from app.agents.base import BaseAgent
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

    exact_casual_patterns = {
        "你好",
        "您好",
        "hi",
        "hello",
        "在吗",
        "谢谢",
        "感谢",
        "你是谁",
        "介绍一下",
    }

    high_risk_keywords = {"作弊", "代考", "代写", "破解", "攻击", "违法", "绕过检测"}

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        message = str(context.get("user_message", "")).strip()
        intent = self.classify(message)
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

    def classify(self, message: str) -> dict[str, Any]:
        rule_result = self._high_precision_rules(message)
        if rule_result is not None and not self._should_consult_llm(message, rule_result, None):
            return self._finalize_result(rule_result, message)

        route_result = self._route_by_examples(message)
        if route_result["confidence"] >= 0.78 and not self._should_consult_llm(message, rule_result, route_result):
            return self._finalize_result(route_result, message)

        llm_result = self._llm_classify(message, route_result)
        if llm_result and (
            self._should_consult_llm(message, rule_result, route_result)
            or llm_result["confidence"] >= max(0.68, route_result["confidence"])
        ):
            return self._finalize_result(llm_result, message)

        if rule_result is not None:
            return self._finalize_result(rule_result, message)
        if route_result["confidence"] >= 0.55:
            return self._finalize_result(route_result, message)
        return self._finalize_result(
            self._result(
                "unknown",
                0.45,
                False,
                "Rule, example routing and model fallback could not classify the request reliably.",
                source="rule_based_fallback",
            ),
            message,
        )

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

    def _has_multi_intent_signal(self, message: str) -> bool:
        text = message.lower()
        signals = [
            ("画像" in text, "profile_update"),
            (any(word in text for word in ("路径", "计划", "方案", "规划")), "learning_plan"),
            (any(word in text for word in ("资源", "资料", "练习")), "resource_request"),
            (any(word in text for word in ("薄弱", "补哪里", "学得很乱", "不会")), "diagnosis"),
        ]
        return len({intent for matched, intent in signals if matched}) >= 2

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
        if not secondary:
            secondary = self._infer_secondary_intents(message, intent)

        needs_clarification = bool(result.get("needs_clarification")) or self._looks_vague(message) or intent == "unknown"
        clarification_question = result.get("clarification_question")
        if needs_clarification and not clarification_question:
            clarification_question = "你希望我先帮你做学习画像、规划路径、推荐资源，还是诊断薄弱点？"

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
        cleaned: list[str] = []
        for item in value:
            intent = str(item)
            if intent == "general_chat":
                intent = "casual_chat"
            if intent in self.allowed_intents and intent not in cleaned and intent != "unknown":
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

    def _extract_entities(self, message: str) -> dict[str, Any]:
        text = message.strip()
        result: dict[str, Any] = {"requested_outputs": []}

        subject_match = re.search(
            r"(?:想学|想学习|学习|入门|复习)\s*([A-Za-z0-9+#\u4e00-\u9fff ]{2,20}?)(?:[，。！？,.、]|请|帮|$)",
            text,
        )
        if subject_match:
            subject = subject_match.group(1).strip("，。！？,. ")
            for suffix in ("基础", "入门"):
                if subject.endswith(suffix) and len(subject) > len(suffix):
                    subject = subject[: -len(suffix)]
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
