"""Knowledge agent — retrieves knowledge points from the course knowledge base.

Stage 2: Falls back to empty context when mock_data is not available.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class KnowledgeAgent(BaseAgent):
    agent_id = "knowledge_agent"
    agent_name = "知识库检索智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        # Try mock_data first (backward compatible)
        mock_diagnosis = self.mock_data.get("diagnosis", {}) if self.mock_data else {}
        weak_points = mock_diagnosis.get("weak_knowledge_points", [])
        retrieved_points = [
            {
                "point_id": item.get("point_id"),
                "name": item.get("name"),
                "priority": item.get("priority"),
            }
            for item in weak_points
        ]

        return {
            "knowledge_context": {
                "course_id": context.get("course_id", ""),
                "retrieved_points": retrieved_points,
                "source": "mock" if retrieved_points else "empty",
            },
            "agent_step": self.agent_step(),
        }

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "knowledge_context": {
                "course_id": (context or {}).get("course_id", ""),
                "retrieved_points": [],
                "source": "fallback",
            },
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": f"KnowledgeAgent fell back to empty context.",
            },
        }
