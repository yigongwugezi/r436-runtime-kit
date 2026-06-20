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

    allowed_intents = set(INTENT_ROUTES) | {"unknown"}

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
        if rule_result is not None:
            return rule_result

        route_result = self._route_by_examples(message)
        if route_result["confidence"] >= 0.78:
            return route_result

        llm_result = self._llm_classify(message)
        if llm_result and llm_result["confidence"] >= max(0.68, route_result["confidence"]):
            return llm_result

        if route_result["confidence"] >= 0.55:
            return route_result
        return self._result("unknown", 0.45, False, "规则、示例路由和模型兜底都无法可靠判断。")

    def _high_precision_rules(self, message: str) -> dict[str, Any] | None:
        text = message.strip().lower()
        compact = "".join(text.split())

        if not compact:
            return self._result("casual_chat", 0.95, False, "用户输入为空或仅为空白。")

        if any(keyword in text for keyword in self.high_risk_keywords):
            return self._result("unsafe", 0.97, False, "命中高风险安全关键词。")

        if compact in self.exact_casual_patterns:
            return self._result("casual_chat", 0.97, False, "命中高置信寒暄表达。")

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

    def _llm_classify(self, message: str) -> dict[str, Any] | None:
        if self.llm_client is None:
            return None

        try:
            route_text = "\n".join(
                f"- {intent}: {route['description']}" for intent, route in INTENT_ROUTES.items()
            )
            content = self.llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是 EduAgent 的意图识别智能体。"
                            "只返回 JSON，不要输出 markdown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请判断用户输入属于哪个意图。\n"
                            f"可选意图：\n{route_text}\n\n"
                            "返回字段：intent, confidence, should_run_agents, reason。\n"
                            f"用户输入：{message}"
                        ),
                    },
                ],
                temperature=0,
                timeout=20,
            )
            parsed = self._load_json(content)
            intent = parsed.get("intent", "unknown")
            if intent not in self.allowed_intents:
                intent = "unknown"
            confidence = float(parsed.get("confidence", 0.6))
            return self._result(
                intent,
                max(0.0, min(1.0, confidence)),
                bool(parsed.get("should_run_agents", intent in ROUTE_AGENT_INTENTS)),
                str(parsed.get("reason", "LLM classified the user intent.")),
            )
        except Exception:
            return None

    def _load_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            raise ValueError("Intent LLM response does not contain JSON.")
        return json.loads(text[start:end])

    def _result(self, intent: str, confidence: float, should_run_agents: bool, reason: str) -> dict[str, Any]:
        if intent not in self.allowed_intents:
            intent = "unknown"
        return {
            "intent": intent,
            "confidence": confidence,
            "should_run_agents": should_run_agents,
            "reason": reason,
        }
