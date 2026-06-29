from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base import AgentValidationError, BaseAgent
from app.utils.profile_normalizer import (
    PROFILE_DIMENSION_LABELS,
    PROFILE_DIMENSION_ORDER,
    clamp_confidence,
    clamp_score,
)


class ProfileAgent(BaseAgent):
    agent_id = "profile_agent"
    agent_name = "Student Profile Agent"

    profile_dimensions = PROFILE_DIMENSION_ORDER
    _MISSING_VALUES = {"", "未知", "未提及", "暂无", "无", "待补充", "无诊断数据", "暂无诊断数据", "unknown", "none", "待诊断", "未诊断"}

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile": self._build_profile(context),
            "agent_step": self.agent_step(),
        }

    def validate_result(self, result: dict[str, Any]) -> None:
        profile = result.get("profile")
        if not isinstance(profile, dict):
            raise AgentValidationError("profile must be a dict")
        keys = [key for key in profile if key in self.profile_dimensions]
        if keys != self.profile_dimensions:
            raise AgentValidationError("profile must expose the stable 9-dimension schema")
        for key in self.profile_dimensions:
            item = profile.get(key)
            if not isinstance(item, dict):
                raise AgentValidationError(f"{key} must be a dict")
            for field in ("value", "score", "confidence", "explanation", "evidence", "source"):
                if field not in item:
                    raise AgentValidationError(f"{key}.{field} is required")

    def _build_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        fallback = self._profile_from_context(context)
        if self.llm_client is None:
            return self._merge_profile_facts(fallback, context)

        try:
            content = self.llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是 EduAgent 的学习画像提取智能体。"
                            "只输出一个 JSON 对象，必须包含以下 9 个顶级键："
                            f"{', '.join(self.profile_dimensions)}。"
                            "每个维度含 key、label、value、score、confidence、explanation、evidence、source。"
                            "score 为 0-100 的整数，confidence 为 0-1 的小数。"
                            "source 可选值：user_input、inferred、llm_generated、diagnosis、feedback。"
                            "必须优先采用学生描述中的具体证据。所有内容用中文撰写。不要输出 Markdown。"
                        ),
                    },
                    {"role": "user", "content": self._profile_prompt(context)},
                ],
            )
            parsed = self._load_json(content)
            self._ensure_complete_llm_profile(parsed)
            normalized = self._normalize_llm_profile(parsed)
            return self._merge_profile_facts(normalized, context)
        except Exception:
            return self._merge_profile_facts(fallback, context)

    def _profile_prompt(self, context: dict[str, Any]) -> str:
        facts = context.get("profile_facts") or {}
        diagnosis = context.get("diagnosis", {}).get("weak_knowledge_points", [])
        facts_lines = []
        if isinstance(facts, dict):
            for key, value in facts.items():
                text = self._clean_profile_fact(key, value)
                if text:
                    facts_lines.append(f"- {key}: {text}")
        weak_lines = []
        for item in diagnosis[:6]:
            if isinstance(item, dict) and item.get("name"):
                name = self._clean_weak_point(item["name"])
                if name:
                    weak_lines.append(f"- {name}")
        return (
            f"Student description:\n{context.get('user_message', '')}\n\n"
            f"Course ID: {context.get('course_id', '')}\n\n"
            "Extracted profile facts:\n"
            f"{chr(10).join(facts_lines) if facts_lines else '- 暂无'}\n\n"
            "Diagnosis weak points:\n"
            f"{chr(10).join(weak_lines) if weak_lines else '- 暂无'}\n"
        )

    def _ensure_complete_llm_profile(self, profile: dict[str, Any]) -> None:
        if not isinstance(profile, dict):
            raise ValueError("profile must be a dict")
        for key in self.profile_dimensions:
            item = profile.get(key)
            if not isinstance(item, dict):
                raise ValueError(f"missing dimension: {key}")
            for field in ("value", "score", "confidence", "explanation", "evidence", "source"):
                if field not in item:
                    raise ValueError(f"missing field: {key}.{field}")

    def _normalize_llm_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key in self.profile_dimensions:
            item = profile.get(key, {})
            value = str(item.get("value", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            evidence = str(item.get("evidence", "")).strip()
            normalized[key] = self._dimension(
                key=key,
                value=value or "待补充",
                score=clamp_score(item.get("score"), 50),
                confidence=clamp_confidence(item.get("confidence"), 0.5),
                source="llm_generated",
                explanation=explanation or value or "模型根据当前对话生成了该维度画像。",
                evidence=evidence or value,
            )
        return normalized

    def _merge_profile_facts(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        facts = context.get("profile_facts") or {}
        if not isinstance(facts, dict):
            return profile

        mapping = {
            "background": "major_background",
            "knowledge_base": "knowledge_base",
            "learning_goal": "learning_goal",
            "preference": "cognitive_style",
            "weak_points": "error_patterns",
            "programming_ability": "coding_ability",
            "target_course": "interest_direction",
            "time_budget": "learning_rhythm",
        }
        for fact_key, profile_key in mapping.items():
            value = self._clean_profile_fact(fact_key, facts.get(fact_key, ""))
            if not value:
                continue
            profile[profile_key] = self._dimension(
                key=profile_key,
                value=value,
                score=self._score_for_dimension(profile_key, value),
                confidence=1.0 if fact_key in {"background", "knowledge_base", "learning_goal", "preference", "weak_points", "target_course", "time_budget"} else 0.9,
                source="user_input",
                explanation=f"该维度直接来自用户描述：{value}",
                evidence=value,
            )
        return profile

    def _profile_from_context(self, context: dict[str, Any]) -> dict[str, Any]:
        facts = context.get("profile_facts") or {}
        if not isinstance(facts, dict):
            facts = {}
        text = str(context.get("user_message", ""))
        course_text = self._course_name(context, facts, text)
        time_budget = self._clean_profile_fact("time_budget", facts.get("time_budget", "")) or self._match_time_budget(text)
        weak_points = self._clean_profile_fact("weak_points", facts.get("weak_points", "")) or self._weak_points_from_diagnosis(context)
        knowledge_base = str(facts.get("knowledge_base", "")).strip() or self._knowledge_base_from_text(text)
        learning_goal = str(facts.get("learning_goal", "")).strip() or self._learning_goal(text, course_text, time_budget)
        preference = str(facts.get("preference", "")).strip() or self._cognitive_style(text)
        background = str(facts.get("background", "")).strip() or self._background_from_text(text)
        coding_ability = str(facts.get("programming_ability", "")).strip() or self._coding_ability(text, knowledge_base)
        interest_direction = self._clean_profile_fact("target_course", facts.get("target_course", "")) or self._interest_direction(text, course_text, weak_points)

        profile = {
            "major_background": self._direct_dimension("major_background", background, "学习者专业或身份背景"),
            "knowledge_base": self._knowledge_dimension(knowledge_base),
            "learning_goal": self._direct_dimension("learning_goal", learning_goal, "当前学习目标"),
            "cognitive_style": self._style_dimension(preference),
            "error_patterns": self._error_dimension(weak_points, course_text),
            "coding_ability": self._coding_dimension(coding_ability),
            "learning_progress": self._progress_dimension(text, course_text, knowledge_base),
            "interest_direction": self._interest_dimension(interest_direction),
            "learning_rhythm": self._rhythm_dimension(time_budget),
        }
        return profile

    def _direct_dimension(self, key: str, value: str, fallback_explanation: str) -> dict[str, Any]:
        value = value.strip()
        if value:
            return self._dimension(
                key=key,
                value=value,
                score=self._score_for_dimension(key, value),
                confidence=0.92,
                source="rule_based_fallback",
                explanation=f"{fallback_explanation}由规则从当前对话中提取。",
                evidence=value,
            )
        return self._dimension(
            key=key,
            value="待补充",
            score=50,
            confidence=0.35,
            source="rule_based_fallback",
            explanation="当前对话中缺少直接信息，可在后续补充。",
            evidence="",
        )

    def _knowledge_dimension(self, value: str) -> dict[str, Any]:
        text = value.strip() or "基础信息待补充"
        source = "user_input" if value.strip() else "rule_based_fallback"
        return self._dimension(
            key="knowledge_base",
            value=text,
            score=self._score_for_dimension("knowledge_base", text),
            confidence=0.9 if value.strip() else 0.4,
            source=source,
            explanation="根据用户提到的已有基础、薄弱点和课程经历总结当前知识基础。",
            evidence=value.strip(),
        )

    def _style_dimension(self, value: str) -> dict[str, Any]:
        text = value.strip() or "偏好图解、练习和代码结合的讲解方式"
        source = "user_input" if value.strip() else "inferred"
        return self._dimension(
            key="cognitive_style",
            value=text,
            score=self._score_for_dimension("cognitive_style", text),
            confidence=0.88 if value.strip() else 0.6,
            source=source,
            explanation="根据用户明确提到的偏好资源形式或讲解方式进行归纳。",
            evidence=value.strip(),
        )

    def _error_dimension(self, weak_points: str, course_text: str) -> dict[str, Any]:
        text = weak_points.strip()
        source = "user_input" if weak_points.strip() else "inferred"
        return self._dimension(
            key="error_patterns",
            value=text,
            score=self._score_for_dimension("error_patterns", text),
            confidence=0.86 if weak_points.strip() else 0.35,
            source=source,
            explanation="由用户明确描述的薄弱点推断易错模式。" if weak_points.strip() else "暂未诊断，待评估。",
            evidence=weak_points.strip(),
        )

    def _coding_dimension(self, value: str) -> dict[str, Any]:
        text = value.strip() or "编程基础待补充"
        source = "user_input" if value.strip() else "inferred"
        return self._dimension(
            key="coding_ability",
            value=text,
            score=self._score_for_dimension("coding_ability", text),
            confidence=0.82 if value.strip() else 0.52,
            source=source,
            explanation="根据用户提到的语言基础、编程经验和课程背景估计编程能力。",
            evidence=value.strip(),
        )

    def _progress_dimension(self, text: str, course_text: str, knowledge_base: str) -> dict[str, Any]:
        if "复习" in text:
            value = f"正在围绕{course_text or '当前课程'}做考前复习"
            confidence = 0.78
        elif any(word in text for word in ["入门", "零基础", "开始"]):
            value = f"处于{course_text or '当前主题'}入门阶段"
            confidence = 0.8
        elif knowledge_base and knowledge_base not in self._MISSING_VALUES:
            value = f"已有部分基础，正在推进{course_text or '当前主题'}"
            confidence = 0.7
        else:
            value = "当前学习进度待进一步确认"
            confidence = 0.45
        return self._dimension(
            key="learning_progress",
            value=value,
            score=self._score_for_dimension("learning_progress", value),
            confidence=confidence,
            source="inferred",
            explanation="根据用户描述的目标、时间和基础推断当前学习阶段。",
            evidence=course_text,
        )

    def _interest_dimension(self, value: str) -> dict[str, Any]:
        text = value.strip() or "兴趣方向待补充"
        source = "user_input" if value.strip() else "inferred"
        return self._dimension(
            key="interest_direction",
            value=text,
            score=self._score_for_dimension("interest_direction", text),
            confidence=0.88 if value.strip() else 0.5,
            source=source,
            explanation="结合目标课程、重点学习主题和用户关注点总结兴趣方向。",
            evidence=value.strip(),
        )

    def _rhythm_dimension(self, value: str) -> dict[str, Any]:
        text = value.strip() or "学习节奏待补充"
        source = "user_input" if value.strip() else "inferred"
        confidence = 0.92 if value.strip() else 0.45
        return self._dimension(
            key="learning_rhythm",
            value=text,
            score=self._score_for_dimension("learning_rhythm", text),
            confidence=confidence,
            source=source,
            explanation="根据用户给出的时间预算和节奏偏好归纳学习安排。",
            evidence=value.strip(),
        )

    def _efficacy_dimension(self, text: str, knowledge_base: str, weak_points: str) -> dict[str, Any]:
        if any(word in text for word in ["有信心", "把握很大", "能搞定"]):
            value = "学习信心较强，愿意主动推进任务"
            confidence = 0.78
        elif any(word in text for word in ["比较弱", "基础一般", "没学过", "零基础", "担心"]):
            value = "当前自我效能感偏保守，需要循序渐进建立信心"
            confidence = 0.76
        elif weak_points:
            value = "对薄弱点有明确认知，适合通过小步验证增强信心"
            confidence = 0.7
        elif knowledge_base and knowledge_base not in self._MISSING_VALUES:
            value = "已有一定基础，自我效能感处于中等水平"
            confidence = 0.62
        else:
            value = "自我效能感待进一步确认"
            confidence = 0.42
        return self._dimension(
            value=value,
            confidence=confidence,
            source="inferred",
            explanation="根据用户对基础、难点和目标难度的表述推断学习信心。",
            evidence=weak_points or knowledge_base,
        )

    def _course_name(self, context: dict[str, Any], facts: dict[str, Any], text: str) -> str:
        course = context.get("course") or {}
        course_name = str(course.get("course_name", "")).strip()
        if course_name:
            return course_name
        fact_course = self._clean_profile_fact("target_course", facts.get("target_course", ""))
        if fact_course:
            return fact_course
        return self._course_from_text(text)

    def _background_from_text(self, text: str) -> str:
        patterns = [
            r"我是([^，。！？\n]{2,32}(?:学生|大一|大二|大三|大四|研究生|本科生))",
            r"本人是([^，。！？\n]{2,32})",
            r"([^，。！？\n]{2,24}专业[^，。！？\n]{0,12}(?:学生|大一|大二|大三|大四))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    def _knowledge_base_from_text(self, text: str) -> str:
        fragments = []
        for pattern in [
            r"([A-Za-z+#一-龥]{1,20}基础(?:比较弱|较弱|一般|还可以|不错|很好)?)",
            r"([A-Za-z+#一-龥]{1,20}(?:没学过|不会|不太会|比较弱))",
        ]:
            for match in re.findall(pattern, text):
                value = match.strip()
                if value and value not in fragments:
                    fragments.append(value)
        return "；".join(fragments)

    def _learning_goal(self, text: str, course_text: str, time_budget: str) -> str:
        if any(word in text for word in ["复习", "考试", "期末", "考研"]):
            return f"希望在{time_budget or '限定时间内'}完成{course_text or '当前课程'}复习"
        if any(word in text for word in ["入门", "了解", "开始学习"]):
            return f"希望在{time_budget or '给定时间内'}入门{course_text or '当前主题'}"
        if course_text:
            return f"系统掌握{course_text}核心内容"
        return ""

    def _cognitive_style(self, text: str) -> str:
        keywords = []
        mapping = {
            "图解": ["图解", "流程图", "可视化"],
            "练习题": ["练习题", "题目", "刷题"],
            "代码案例": ["代码", "案例", "实操", "实验"],
            "讲义": ["讲义", "总结", "笔记"],
        }
        for label, words in mapping.items():
            if any(word in text for word in words):
                keywords.append(label)
        return "、".join(keywords)

    def _coding_ability(self, text: str, knowledge_base: str) -> str:
        items = []
        for keyword in ["Python", "C语言", "C++", "Java", "编程", "代码"]:
            if keyword in text or keyword in knowledge_base:
                items.append(keyword)
        if "基础一般" in text:
            items.append("基础一般")
        if any(word in text for word in ["比较弱", "较弱", "不太会", "不会", "零基础"]):
            items.append("需要从基础练习开始")
        return "；".join(dict.fromkeys(items))

    def _interest_direction(self, text: str, course_text: str, weak_points: str) -> str:
        focus_match = re.search(r"重点(?:学习|补|复习)?([^，。！？\n]{2,40})", text)
        if focus_match:
            return focus_match.group(1).strip()
        if weak_points:
            return weak_points
        return course_text

    def _match_time_budget(self, text: str) -> str:
        match = re.search(r"(每天\s*(?:\d+|[一二两三四五六七八九十半]+)\s*(?:个)?小时|(?:\d+|[一二两三四五六七八九十半]+)\s*(?:个)?(?:月|个月|天|周|星期|小时))", text)
        return match.group(1).strip() if match else ""

    def _weak_points_from_diagnosis(self, context: dict[str, Any]) -> str:
        weak_points = context.get("diagnosis", {}).get("weak_knowledge_points", [])
        names = [self._clean_weak_point(item.get("name", "")) for item in weak_points if isinstance(item, dict) and item.get("name")]
        return "、".join(name for name in names if name)

    def _course_from_text(self, text: str) -> str:
        for course in [
            "微积分",
            "高等数学",
            "线性代数",
            "数据结构",
            "人工智能导论",
            "人工智能",
            "机器学习",
            "神经网络",
            "自然语言处理",
            "深度学习",
            "操作系统",
            "计算机网络",
        ]:
            if course in text:
                return course
        return ""

    def _clean_profile_fact(self, key: str, value: Any) -> str:
        text = str(value or "").strip()
        if self._is_missing_value(text):
            return ""
        if key == "target_course":
            return self._clean_course_name(text)
        if key == "weak_points":
            return self._clean_weak_point(text)
        if key == "time_budget":
            return text if self._match_time_budget(text) else ""
        return text

    def _clean_course_name(self, text: str) -> str:
        for course in ["微积分", "高等数学", "线性代数", "数据结构", "机器学习", "人工智能导论", "人工智能", "深度学习", "操作系统", "计算机网络"]:
            if course in text:
                return course
        return re.sub(r"^(?:我(?:想|要|准备)?|帮我)?(?:想|要|准备)?(?:学习|学|补一下|补|复习|入门|掌握|了解)+", "", text).strip()

    def _clean_weak_point(self, value: Any) -> str:
        text = str(value or "").strip()
        return "" if self._is_missing_value(text) else text

    def _is_missing_value(self, value: str) -> bool:
        return value.strip().lower() in self._MISSING_VALUES

    def _dimension(
        self,
        key: str,
        value: str,
        score: int,
        confidence: float,
        source: str,
        explanation: str,
        evidence: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": PROFILE_DIMENSION_LABELS[key],
            "value": value.strip() if key == "error_patterns" else value.strip() or "待补充",
            "score": clamp_score(score, 50),
            "confidence": clamp_confidence(confidence, 0.5),
            "explanation": explanation.strip() or value.strip() or "待补充",
            "evidence": evidence.strip(),
            "source": source.strip() or "rule_based_fallback",
        }

    def _score_for_dimension(self, key: str, value: str) -> int:
        text = value.strip()
        if not text or text in self._MISSING_VALUES:
            return 50
        low_words = ["零基础", "不会", "比较弱", "较弱", "一般", "待补充", "薄弱", "不足", "入门"]
        high_words = ["熟悉", "掌握", "较好", "不错", "扎实", "系统", "有信心"]
        if key in {"knowledge_base", "coding_ability"}:
            if any(word in text for word in low_words):
                return 42
            if any(word in text for word in high_words):
                return 78
            return 60
        if key == "error_patterns":
            return 38 if any(word in text for word in ["薄弱", "不会", "错误"]) else 52
            if any(word in text for word in ["有信心", "主动"]):
                return 76
            if any(word in text for word in ["保守", "较弱", "担心"]):
                return 44
            return 58
        if key in {"learning_goal", "interest_direction"}:
            return 82 if len(text) >= 4 else 68
        if key == "learning_rhythm":
            return 74 if re.search(r"\d+\s*(小时|天|周|个月)", text) else 56
        if key == "learning_progress":
            return 48 if any(word in text for word in ["入门", "开始"]) else 62
        return 70 if len(text) >= 4 else 58

    def _load_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            raise ValueError("LLM response does not contain a JSON object.")
        return json.loads(text[start:end])
