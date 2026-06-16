"""Diagnosis agent — identifies weak knowledge points and recommends strategies.

Stage 2: Falls back to empty diagnosis when mock_data is not available.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class DiagnosisAgent(BaseAgent):
    agent_id = "diagnosis_agent"
    agent_name = "学习诊断智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        diagnosis = (self.mock_data or {}).get("diagnosis", {}) if self.mock_data else {}
        return {
            "diagnosis": diagnosis,
            "agent_step": self.agent_step(),
        }

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "diagnosis": {
                "weak_knowledge_points": [],
                "recommended_strategy": "",
                "source": "fallback",
            },
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": "DiagnosisAgent fell back to empty diagnosis.",
            },
        }
