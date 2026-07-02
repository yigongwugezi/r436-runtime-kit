"""Executable multimodal tools and provider placeholders.

The non-text providers intentionally refuse to fake outputs when credentials
are missing or when the real API call is not implemented yet.
"""

from __future__ import annotations

import os
import re
from typing import Any


def _response(
    *,
    status: str,
    provider: str,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "provider": provider,
        "result": result,
        "warnings": warnings or [],
        "trace": trace or {},
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_mermaid_label(value: Any) -> str:
    text = _text(value) or "未命名"
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = text.replace("(", "（").replace(")", "）")
    return text[:80]


def _normalize_stages(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("stages") or value.get("learning_path") or []
    if not isinstance(value, list):
        return []

    stages: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title") or item.get("name") or f"阶段 {index}")
        tasks = item.get("tasks") or item.get("nodes") or item.get("knowledge_points") or []
        children: list[str] = []
        if isinstance(tasks, list):
            for task in tasks:
                if isinstance(task, dict):
                    child = _text(task.get("topic") or task.get("title") or task.get("name"))
                else:
                    child = _text(task)
                if child:
                    children.append(child)
        stages.append({
            "title": title,
            "goal": _text(item.get("goal") or item.get("objective") or item.get("description")),
            "children": children[:8],
        })
    return stages


class MindMapTool:
    name = "MindMapTool"
    provider = "local_mindmap"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        learning_path = context.get("learning_path") or context.get("path")
        stages = _normalize_stages(learning_path)
        topic = _text(context.get("topic") or context.get("course_name") or context.get("subject_name"))

        if not stages:
            knowledge_context = context.get("knowledge_context") or {}
            points = []
            if isinstance(knowledge_context, dict):
                points = (
                    knowledge_context.get("retrieved_points")
                    or knowledge_context.get("knowledge_points")
                    or knowledge_context.get("topics")
                    or []
                )
            if isinstance(points, list) and points:
                stages = [
                    {
                        "title": _text(point.get("title") if isinstance(point, dict) else point),
                        "goal": "",
                        "children": [],
                    }
                    for point in points[:12]
                    if _text(point.get("title") if isinstance(point, dict) else point)
                ]
                topic = topic or _text(knowledge_context.get("course_name") if isinstance(knowledge_context, dict) else "")

        if not stages:
            return _response(
                status="needs_input",
                provider=self.provider,
                warnings=["缺少可用于生成思维导图的 learning_path 或 knowledge_context。"],
                trace={"input_keys": sorted(context.keys())},
            )

        root = topic or _text(context.get("user_message")) or "学习路径"
        children = [
            {
                "title": stage["title"],
                "children": [{"title": child} for child in stage["children"]],
            }
            for stage in stages
        ]
        lines = ["mindmap", f"  root(({_safe_mermaid_label(root)}))"]
        for stage in stages:
            lines.append(f"    {_safe_mermaid_label(stage['title'])}")
            for child in stage["children"][:6]:
                lines.append(f"      {_safe_mermaid_label(child)}")

        return _response(
            status="success",
            provider=self.provider,
            result={
                "mindmap_json": {"title": root, "children": children},
                "mermaid": "\n".join(lines),
                "stage_count": len(stages),
            },
            trace={"source": "learning_path" if learning_path else "knowledge_context"},
        )


class QwenVisionProvider:
    name = "QwenVisionProvider"
    provider = "qwen_vision"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("QWEN_API_KEY")
        model = os.getenv("QWEN_VL_MODEL")
        base_url = os.getenv("QWEN_BASE_URL")
        if not api_key or not model or not base_url:
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["Qwen vision provider is not configured."],
                trace={"required_env": ["QWEN_API_KEY", "QWEN_VL_MODEL", "QWEN_BASE_URL"]},
            )
        if not context.get("attachments"):
            return _response(
                status="needs_input",
                provider=self.provider,
                warnings=["缺少图片附件，无法执行图片理解。"],
            )
        return _response(
            status="unsupported",
            provider=self.provider,
            warnings=["Qwen vision API call is not implemented yet; no fake recognition result was returned."],
            trace={"model": model, "base_url": base_url},
        )


class QwenImageProvider:
    name = "QwenImageProvider"
    provider = "qwen_image"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("QWEN_API_KEY")
        model = os.getenv("QWEN_IMAGE_MODEL")
        base_url = os.getenv("QWEN_BASE_URL")
        if not api_key or not model or not base_url:
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["Qwen image provider is not configured."],
                trace={"required_env": ["QWEN_API_KEY", "QWEN_IMAGE_MODEL", "QWEN_BASE_URL"]},
            )
        return _response(
            status="unsupported",
            provider=self.provider,
            warnings=["Qwen image API call is not implemented yet; no fake image_url was returned."],
            trace={"model": model, "base_url": base_url},
        )


class WanVideoProvider:
    name = "WanVideoProvider"
    provider = "wan_video"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("WAN_API_KEY")
        provider = os.getenv("WAN_PROVIDER")
        model = os.getenv("WAN_VIDEO_MODEL")
        if not api_key or not provider or not model:
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["Wan video provider is not configured."],
                trace={"required_env": ["WAN_API_KEY", "WAN_PROVIDER", "WAN_VIDEO_MODEL"]},
            )
        return _response(
            status="unsupported",
            provider=self.provider,
            warnings=["Wan video API call is not implemented yet; no fake video_url was returned."],
            trace={"provider": provider, "model": model},
        )
