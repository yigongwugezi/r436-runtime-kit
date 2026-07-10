"""Thin multimodal agent adapter.

It does not fake model output. It only routes a multimodal task to the
configured local/provider tool and returns the tool status as-is.
"""

from __future__ import annotations

from typing import Any

from app.services.multimodal_registry import ToolRegistry, default_registry


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_image(context: dict[str, Any]) -> bool:
    return bool(context.get("attachments") or context.get("image_url") or context.get("image_base64"))


def _infer_task_type(context: dict[str, Any]) -> str:
    explicit = _text(context.get("task_type"))
    if explicit:
        return explicit

    message = _text(context.get("user_message"))
    has_image = _has_image(context)

    if any(word in message for word in ("微课", "视频", "动画", "分镜")):
        return "video_script_generation"
    if any(word in message for word in ("生成图片", "画图", "配图", "讲解图")):
        return "teaching_diagram_generation"
    if any(word in message for word in ("思维导图", "知识图谱", "脑图")):
        return "image_to_mindmap" if has_image else "mindmap_generation"

    if has_image:
        if any(word in message for word in ("资源包", "整理成资源", "学习资源")):
            return "image_to_resource_bundle"
        if any(word in message for word in ("错题", "错因", "哪里错")):
            return "image_wrong_question_analysis"
        if any(word in message for word in ("讲解", "怎么做", "答案", "解题")):
            return "explain_image_question"
        if any(word in message for word in ("计划", "路径", "安排")):
            return "image_to_learning_plan"
        if any(word in message for word in ("变式", "类似题", "练习题")):
            return "image_to_variant_questions"
        if any(word in message for word in ("卡片", "闪卡")):
            return "image_to_flashcards"
        if any(word in message for word in ("笔记", "总结")):
            return "image_note_summary"
        return "image_understanding"

    if any(word in message for word in ("这张图", "图片", "题图", "图中", "这道题")):
        return "image_understanding"
    return "mindmap_generation"


class MultimodalAgent:
    """Route multimodal requests to the existing tool registry."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        task_type = _infer_task_type(context)
        tool_name, tool = self.registry.select_tool(task_type)
        if not tool:
            return {
                "status": "unsupported",
                "provider": "none",
                "task_type": task_type,
                "tool": "",
                "warnings": [f"No multimodal tool registered for task_type={task_type}."],
                "result": {},
                "trace": {"input_keys": sorted(context.keys())},
            }

        result = tool.run({**context, "task_type": task_type})
        if not isinstance(result, dict):
            result = {"status": "failed", "provider": tool_name or "unknown", "warnings": ["Tool returned non-dict result."], "result": {}}
        return {
            "task_type": task_type,
            "tool": tool_name or "",
            **result,
        }
