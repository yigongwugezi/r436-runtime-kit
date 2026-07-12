"""Small registry for multimodal tools."""

from __future__ import annotations

from typing import Any

from app.services.multimodal_provider import (
    MindMapTool,
    QwenImageProvider,
    QwenVisionProvider,
    WanVideoProvider,
)
from app.services.spark_provider import (
    SparkImageProvider,
    SparkVideoProvider,
)
from app.services.multimodal_provider import SparkVisionProvider


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._task_map: dict[str, str] = {
            "mindmap_generation": "MindMapTool",
            "image_understanding": "QwenVisionProvider",
            "image_to_mindmap": "QwenVisionProvider",
            "note_image_to_mindmap": "QwenVisionProvider",
            "question_image_to_mindmap": "QwenVisionProvider",
            "image_to_flashcards": "QwenVisionProvider",
            "note_image_to_flashcards": "QwenVisionProvider",
            "question_image_to_flashcards": "QwenVisionProvider",
            "explain_image_question": "QwenVisionProvider",
            "solve_image_question": "QwenVisionProvider",
            "image_wrong_question_analysis": "QwenVisionProvider",
            "image_note_summary": "QwenVisionProvider",
            "image_to_learning_plan": "QwenVisionProvider",
            "image_to_variant_questions": "QwenVisionProvider",
            "image_to_resource_bundle": "QwenVisionProvider",
            "image_generation": "SparkImageProvider",      # 科大讯飞星火绘画
            "concept_card_generation": "SparkImageProvider",
            "teaching_diagram_generation": "SparkImageProvider",
            "video_generation": "SparkVideoProvider",        # 科大讯飞星火视频
            "micro_lesson_video": "SparkVideoProvider",
            "video_script_generation": "SparkVideoProvider",
            # Spark vision as alternative to Qwen VL
            "image_understanding_spark": "SparkVisionProvider",
            "image_to_mindmap_spark": "SparkVisionProvider",
            # Fallback to Qwen/Wan when Spark not configured
            "image_generation_qwen": "QwenImageProvider",
            "video_generation_wan": "WanVideoProvider",
        }

    def register_tool(self, name: str, tool: Any) -> None:
        self._tools[name] = tool

    def get_tool(self, name: str) -> Any | None:
        return self._tools.get(name)

    def select_tool(self, task_type: str) -> tuple[str | None, Any | None]:
        name = self._task_map.get(task_type)
        tool = self.get_tool(name) if name else None
        # 如果 Spark 没配置，自动回退到备用 provider
        if tool and hasattr(tool, 'run'):
            return name, tool
        if name and name.startswith("Spark"):
            fallback = self._task_map.get(task_type + "_qwen") or self._task_map.get(task_type + "_wan")
            if fallback:
                return fallback, self.get_tool(fallback)
        return name, tool


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool("MindMapTool", MindMapTool())
    registry.register_tool("QwenVisionProvider", QwenVisionProvider())
    registry.register_tool("QwenImageProvider", QwenImageProvider())
    registry.register_tool("WanVideoProvider", WanVideoProvider())
    registry.register_tool("SparkImageProvider", SparkImageProvider())
    registry.register_tool("SparkVideoProvider", SparkVideoProvider())
    registry.register_tool("SparkVisionProvider", SparkVisionProvider())
    return registry
