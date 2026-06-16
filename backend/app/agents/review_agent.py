"""Review agent — quality-checks generated resources and paths before delivery.

Stage 2: Falls back to empty review when mock_data is not available.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class ReviewAgent(BaseAgent):
    agent_id = "review_agent"
    agent_name = "质量审核智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        review = (self.mock_data or {}).get("review", {}) if self.mock_data else {}
        return {
            "review": review,
            "agent_step": self.agent_step(),
        }

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "review": {
                "passed": True,
                "warnings": [],
                "source": "fallback",
            },
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": "ReviewAgent fell back to default review.",
            },
        }
