"""Resource agent — generates or retrieves learning resources for each path stage.

Stage 2: Falls back to empty resource list when mock_data is unavailable.
The orchestrator now passes the LLM client to this agent for real generation.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class ResourceAgent(BaseAgent):
    agent_id = "resource_agent"
    agent_name = "学习资源生成智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        resources = (self.mock_data or {}).get("resources", []) if self.mock_data else []

        # Future: use self.llm_client.chat() for real resource generation
        # when mock_data is empty and llm_client is available.

        return {
            "resources": resources,
            "agent_step": self.agent_step(),
        }

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "resources": [],
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "failed",
                "summary": "ResourceAgent fell back to empty resource list.",
            },
        }
