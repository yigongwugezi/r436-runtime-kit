"""Planner agent — generates a personalised learning path from profile and diagnosis.

Stage 2: Falls back to empty path when mock_data is not available.
In a future step this agent will use the LLM client for real path generation.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    agent_id = "planner_agent"
    agent_name = "学习路径规划智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        learning_path = (self.mock_data or {}).get("learning_path", []) if self.mock_data else []
        return {
            "learning_path": learning_path,
            "agent_step": self.agent_step(),
        }

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "learning_path": [],
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": "PlannerAgent fell back to empty path.",
            },
        }
