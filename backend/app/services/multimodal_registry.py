"""Small registry for multimodal tools."""

from __future__ import annotations

from typing import Any

from app.services.multimodal_provider import (
    MindMapTool,
    QwenImageProvider,
    QwenVisionProvider,
    WanVideoProvider,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._task_map: dict[str, str] = {
            "mindmap_generation": "MindMapTool",
            "image_understanding": "QwenVisionProvider",
            "image_generation": "QwenImageProvider",
            "video_generation": "WanVideoProvider",
        }

    def register_tool(self, name: str, tool: Any) -> None:
        self._tools[name] = tool

    def get_tool(self, name: str) -> Any | None:
        return self._tools.get(name)

    def select_tool(self, task_type: str) -> tuple[str | None, Any | None]:
        name = self._task_map.get(task_type)
        return name, self.get_tool(name) if name else None


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool("MindMapTool", MindMapTool())
    registry.register_tool("QwenVisionProvider", QwenVisionProvider())
    registry.register_tool("QwenImageProvider", QwenImageProvider())
    registry.register_tool("WanVideoProvider", WanVideoProvider())
    return registry
