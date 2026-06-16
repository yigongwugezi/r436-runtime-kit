import json
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
        "error_patterns",
        "coding_ability",
        "learning_progress",
        "interest_direction",
        "learning_rhythm",
        "self_efficacy",
    ]

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile": self._build_profile(context),
            "agent_step": self.agent_step(),
        }

    def _build_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.llm_client is None:
            return self._safe_fallback()

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
            return self._safe_fallback()

    def _safe_fallback(self) -> dict[str, Any]:
        """Return mock profile data, or a minimal empty profile if mock is unavailable."""
        mock_profile = self.mock_data.get("profile") if isinstance(self.mock_data, dict) else None
        if isinstance(mock_profile, dict) and mock_profile:
            return mock_profile
        # Absolute last resort — minimal profile so downstream agents don't crash
        return {
            key: {
                "label": key,
                "value": "未提取",
                "confidence": 0.5,
                "source": "inferred",
                "evidence": "fallback",
            }
            for key in self.profile_dimensions
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

        # Strip markdown code fences (handle ```json, ```JSON, ```, etc.)
        if text.startswith("```"):
            # Find the first newline to strip the opening fence line
            fence_end = text.find("\n")
            if fence_end != -1:
                text = text[fence_end + 1:]
            # Strip closing fence
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].strip()

        # Try to find a JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            raise ValueError("LLM response does not contain a JSON object.")

        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            # Last resort: try to fix common LLM JSON issues
            candidate = text[start:end]
            # Remove trailing commas before closing braces/brackets
            import re
            candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                raise ValueError(
                    f"Failed to parse LLM JSON response: {exc}. "
                    f"Raw snippet: {candidate[:200]}..."
                ) from exc

    def _normalize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = {}
        fallback = self.mock_data.get("profile") if isinstance(self.mock_data, dict) else {}
        if not isinstance(fallback, dict):
            fallback = {}

        for key in self.profile_dimensions:
            item = profile.get(key)
            fallback_item = fallback.get(key, {}) if isinstance(fallback, dict) else {}
            if not isinstance(item, dict):
                item = {}
            if not isinstance(fallback_item, dict):
                fallback_item = {}

            normalized[key] = {
                "label": item.get("label") or fallback_item.get("label", key),
                "value": item.get("value") or fallback_item.get("value", ""),
                "confidence": float(item.get("confidence", fallback_item.get("confidence", 0.5))),
                "source": item.get("source") or "llm",
                "evidence": item.get("evidence") or fallback_item.get("evidence", ""),
            }

        return normalized
