"""Small registry for multimodal tools."""

from __future__ import annotations

from typing import Any

from app.services.multimodal_provider import (
    ManimVideoProvider,
    MindMapTool,
    QwenImageProvider,
    QwenVisionProvider,
    SeedreamImageProvider,
    WanVideoProvider,
)
from app.services.spark_provider import (
    SparkImageProvider,
)
from app.services.multimodal_provider import SparkVisionProvider
from app.services.code2video_provider import Code2VideoProvider


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
            # ── 生成类 ──
            "image_generation": "SparkImageProvider",
            "concept_card_generation": "SparkImageProvider",
            "teaching_diagram_generation": "SparkImageProvider",
            "image_generation_seedream": "SeedreamImageProvider",
            "image_generation_qwen": "QwenImageProvider",
            "concept_card_generation_qwen": "QwenImageProvider",
            "teaching_diagram_generation_qwen": "QwenImageProvider",
            "video_generation": "Code2VideoProvider",
            "micro_lesson_video": "Code2VideoProvider",
            "video_script_generation": "Code2VideoProvider",
            # ── 备用 / 直连 ──
            "image_understanding_spark": "SparkVisionProvider",
            "image_to_mindmap_spark": "SparkVisionProvider",
            "image_generation_spark": "SparkImageProvider",
            "video_generation_wan": "WanVideoProvider",
            "video_generation_manim": "ManimVideoProvider",
            "video_generation_code2video": "Code2VideoProvider",
        }

    def register_tool(self, name: str, tool: Any) -> None:
        self._tools[name] = tool

    def get_tool(self, name: str) -> Any | None:
        return self._tools.get(name)

    def select_tool(self, task_type: str) -> tuple[str | None, Any | None]:
        """Select the best configured tool for a task type.

        Tries the primary mapping first.  If the provider is not configured,
        falls back through suffixed alternatives checking configuration each time.
        """
        name = self._task_map.get(task_type)
        tool = self.get_tool(name) if name else None
        if tool is not None and self._is_configured(tool):
            return name, tool

        # Primary is registered but not configured — try suffixed alternatives
        for suffix in ("_qwen", "_wan", "_spark"):
            fname = self._task_map.get(task_type + suffix)
            ftool = self.get_tool(fname) if fname else None
            if ftool is not None and self._is_configured(ftool):
                return fname, ftool

        # Nothing configured — return primary so run() can surface the
        # "provider_not_configured" status instead of a generic "unsupported".
        return name, tool

    @staticmethod
    def _is_configured(tool: Any) -> bool:
        """Check whether a tool reports itself as configured.

        Returns True for tools without an is_configured() method
        (backward compatibility).
        """
        checker = getattr(tool, "is_configured", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return True


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool("MindMapTool", MindMapTool())
    registry.register_tool("QwenVisionProvider", QwenVisionProvider())
    registry.register_tool("SeedreamImageProvider", SeedreamImageProvider())
    registry.register_tool("QwenImageProvider", QwenImageProvider())
    registry.register_tool("WanVideoProvider", WanVideoProvider())
    registry.register_tool("ManimVideoProvider", ManimVideoProvider())
    registry.register_tool("Code2VideoProvider", Code2VideoProvider())
    registry.register_tool("SparkImageProvider", SparkImageProvider())
    registry.register_tool("SparkVisionProvider", SparkVisionProvider())
    return registry
