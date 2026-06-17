from typing import Any

from app.agents.base import BaseAgent


class DiagnosisAgent(BaseAgent):
    agent_id = "diagnosis_agent"
    agent_name = "学习诊断智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        points = list(context.get("knowledge_context", {}).get("retrieved_points", []))
        if not points:
            points = self.mock_data["diagnosis"].get("weak_knowledge_points", [])

        profile = context.get("profile", {})
        knowledge_base = str(profile.get("knowledge_base", {}).get("value", ""))
        weak_text = str(profile.get("weak_points", {}).get("value", ""))
        goal = str(profile.get("learning_goal", {}).get("value", ""))

        weak_points = []
        for index, point in enumerate(points[:4], start=1):
            priority = "high" if index <= 2 or self._looks_weak(point, weak_text, knowledge_base) else "medium"
            weak_points.append(
                {
                    "point_id": point.get("point_id", f"point_{index}"),
                    "chapter_id": point.get("chapter_id"),
                    "name": point.get("name", f"重点知识点 {index}"),
                    "reason": self._reason(point, weak_text, knowledge_base, goal),
                    "priority": priority,
                    "difficulty": point.get("difficulty", "medium"),
                    "prerequisites": point.get("prerequisites", []),
                }
            )

        summary_names = "、".join(str(item.get("name")) for item in weak_points[:3])
        diagnosis = {
            "summary": (
                f"系统根据当前学习画像和课程知识库，优先定位了 {summary_names}。"
                "建议先补齐前置概念，再进入练习和实操，避免直接刷题导致理解断层。"
            ),
            "weak_knowledge_points": weak_points,
            "recommended_strategy": self._strategy(profile, weak_points),
        }
        return {
            "diagnosis": diagnosis,
            "agent_step": self.agent_step(),
        }

    def _looks_weak(self, point: dict[str, Any], weak_text: str, knowledge_base: str) -> bool:
        name = str(point.get("name", ""))
        haystack = f"{weak_text} {knowledge_base}"
        return any(token and token in haystack for token in name.replace("与", " ").replace("、", " ").split())

    def _reason(self, point: dict[str, Any], weak_text: str, knowledge_base: str, goal: str) -> str:
        name = point.get("name", "该知识点")
        if weak_text and any(word in weak_text for word in ["不会", "薄弱", "弱", "不懂"]):
            return f"学生反馈存在薄弱点，且 {name} 是当前课程路径中的关键前置内容。"
        if knowledge_base:
            return f"学生已有基础为“{knowledge_base}”，需要通过 {name} 连接已有知识和学习目标。"
        if goal:
            return f"学习目标为“{goal}”，{name} 是达成该目标前需要先掌握的内容。"
        return f"{name} 是课程知识库中靠前且依赖较多的基础内容。"

    def _strategy(self, profile: dict[str, Any], weak_points: list[dict[str, Any]]) -> str:
        preference = str(profile.get("cognitive_style", {}).get("value", ""))
        if any(word in preference for word in ["图解", "代码", "实操"]):
            return "采用“概念讲解 -> 图解结构 -> 代码/练习验证”的顺序，匹配学生偏好的学习方式。"
        if weak_points:
            return "采用“先补高优先级薄弱点，再做章节练习，最后复盘错题”的学习策略。"
        return "采用从基础概念到实践任务的渐进式学习策略。"
