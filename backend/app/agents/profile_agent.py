import json
import re
from typing import Any

from app.agents.base import BaseAgent


class ProfileAgent(BaseAgent):
    agent_id = "profile_agent"
    agent_name = "Student Profile Agent"

    profile_dimensions = [
        "major_background",
        "knowledge_base",
        "learning_goal",
        "cognitive_style",
        "weak_points",
        "programming_ability",
        "learning_progress",
        "interests",
    ]

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile": self._build_profile(context),
            "agent_step": self.agent_step(),
        }

    def _build_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.llm_client is None:
            return self._profile_from_prompt(context["user_message"])

        try:
            content = self.llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是高等教育个性化学习系统中的学生画像智能体。"
                            "你的任务是从学生自然语言描述中抽取学习画像。"
                            "如果原文出现了专业、年级、基础、目标、偏好、薄弱点，必须直接提取，"
                            "不要把已经出现的信息写成未知。只返回 JSON，不要使用 markdown 代码块。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": self._profile_prompt(context["user_message"]),
                    },
                ],
            )
            parsed = self._load_json(content)
            return self._normalize_profile(parsed)
        except Exception:
            return self._profile_from_prompt(context["user_message"])

    def _profile_from_prompt(self, prompt: str) -> dict[str, Any]:
        background = self._extract_value(prompt, "身份/专业背景")
        target_course = self._extract_value(prompt, "目标课程/知识方向")
        knowledge_base = self._extract_value(prompt, "已有基础")
        weak_points = self._extract_value(prompt, "薄弱点")
        learning_goal = self._extract_value(prompt, "学习目标")
        preference = self._extract_value(prompt, "学习偏好")

        if not background:
            background_match = re.search(r"我是([^，。,.!?！？\n]{2,30}(?:学生|本科生|研究生|大一|大二|大三|大四))", prompt)
            background = background_match.group(1) if background_match else ""
        if not target_course:
            course_match = re.search(r"想学(?:习)?([^，。,.!?！？\n]{2,24})", prompt)
            target_course = course_match.group(1) if course_match else ""
        if not target_course:
            target_course = self._course_from_text(prompt)
        if not learning_goal and "考试" in prompt:
            learning_goal = "考试通过"

        return {
            "major_background": self._dimension("专业背景", background),
            "knowledge_base": self._dimension("知识基础", knowledge_base or target_course),
            "learning_goal": self._dimension("学习目标", learning_goal or target_course),
            "cognitive_style": self._dimension("认知风格", preference),
            "weak_points": self._dimension("薄弱点", weak_points),
            "programming_ability": self._dimension("编程能力", self._programming_value(prompt)),
            "learning_progress": self._dimension(
                "学习进度",
                f"刚开始学习{target_course}" if target_course else "",
            ),
            "interests": self._dimension("兴趣偏好", target_course or preference),
        }

    def _extract_value(self, prompt: str, label: str) -> str:
        pattern = rf"{re.escape(label)}[：:]\s*([^\n]+)"
        match = re.search(pattern, prompt)
        return match.group(1).strip(" -") if match else ""

    def _programming_value(self, prompt: str) -> str:
        items = []
        for keyword in ["Python", "PYTHON", "Java", "C++", "代码", "编程"]:
            if keyword in prompt:
                items.append(keyword)
        return "、".join(dict.fromkeys(items))

    def _course_from_text(self, prompt: str) -> str:
        for course in [
            "数据结构",
            "机器学习",
            "人工智能导论",
            "人工智能",
            "深度学习",
            "神经网络",
            "Python",
            "线性代数",
            "计算机网络",
            "操作系统",
            "数据库",
        ]:
            if course in prompt:
                return course
        return ""

    def _dimension(self, label: str, value: str) -> dict[str, Any]:
        value = value.strip()
        if not value:
            return {
                "label": label,
                "value": "未知",
                "confidence": 0.0,
                "source": "unknown",
                "evidence": "",
            }
        return {
            "label": label,
            "value": value,
            "confidence": 1.0,
            "source": "user_input",
            "evidence": value,
        }

    def _profile_prompt(self, user_message: str) -> str:
        dimensions = ", ".join(self.profile_dimensions)
        return (
            "学生原始描述：\n"
            f"{user_message}\n\n"
            "请返回一个 JSON 对象，顶层必须且只能包含这些 key：\n"
            f"{dimensions}\n\n"
            "每个 key 的值必须是对象，包含这些字段："
            "label, value, confidence, source, evidence。\n"
            "要求：\n"
            "1. label 用中文短标签。\n"
            "2. value 用中文概括，优先使用学生原话中的信息。\n"
            "3. confidence 是 0 到 1 的数字。\n"
            "4. source 如果来自原文，写 user_input；如果是推断，写 inferred。\n"
            "5. evidence 写对应的学生原话片段或推断依据。\n"
            "6. 不要输出解释文字，不要输出 markdown，只输出 JSON。"
        )

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

    def _normalize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = {}

        for key in self.profile_dimensions:
            item = profile.get(key)
            if not isinstance(item, dict) or not str(item.get("value", "")).strip():
                # Missing or empty dimension — use a neutral sentinel, never mock data
                normalized[key] = {
                    "label": key,
                    "value": "未知",
                    "confidence": 0.0,
                    "source": "unknown",
                    "evidence": "",
                }
                continue

            normalized[key] = {
                "label": item.get("label", key),
                "value": str(item.get("value", "")),
                "confidence": float(item.get("confidence", 0.5)),
                "source": item.get("source", "llm"),
                "evidence": str(item.get("evidence", "")),
            }

        return normalized
