"""Thin multimodal agent adapter.

It does not fake model output. It only routes a multimodal task to the
configured local/provider tool and returns the tool status as-is.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent, register_agent
from app.services.multimodal_registry import ToolRegistry, default_registry


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_image(context: dict[str, Any]) -> bool:
    return bool(context.get("attachments") or context.get("image_url") or context.get("image_base64"))


def _infer_task_type(context: dict[str, Any]) -> str:
    explicit = _text(context.get("task_type"))
    if explicit:
        return {"image_explanation": "explain_image_question"}.get(explicit, explicit)

    message = _text(context.get("user_message"))
    has_image = _has_image(context)

    if any(word in message for word in ("微课", "视频", "动画", "分镜", "短视频", "讲解视频")):
        return "video_generation"
    if any(word in message for word in ("生成图片", "画图", "配图", "讲解图", "插图", "图示", "图片")):
        return "image_generation"
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


def _public_status(status: Any) -> tuple[str, str | None]:
    """Expose a small provider-agnostic status contract to the UI."""
    raw_status = _text(status) or "failed"
    if raw_status in {"success", "partial_success", "needs_manual_review", "script_ready", "submitted"}:
        return "completed", None
    if raw_status in {"provider_not_configured", "script_ready_provider_not_configured"}:
        return "provider_not_configured", None
    if raw_status == "needs_input":
        return "generation_failed", "missing_input"
    if raw_status == "unsupported":
        return "generation_failed", "unsupported"
    return "generation_failed", raw_status


def _result_content(result: dict[str, Any]) -> tuple[str, str | None]:
    for key in ("display_text", "teaching_text", "answer_text", "chat_text", "markdown", "script"):
        text = _text(result.get(key))
        if text:
            return text, None
    for key in ("video_url", "image_url"):
        url = _text(result.get(key))
        if url:
            return "", url
    image_urls = result.get("image_urls")
    if isinstance(image_urls, list) and image_urls:
        return "", _text(image_urls[0]) or None
    return "", None


class MultimodalAgent:
    """Route multimodal requests to the existing tool registry."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        task_type = _infer_task_type(context)
        # ── 允许前端/上下文指定生图 Provider ──
        _GEN_TASKS = {"image_generation", "teaching_diagram_generation", "concept_card_generation"}
        if task_type in _GEN_TASKS:
            provider = _text(context.get("provider") or context.get("image_provider"))
            if provider and provider != "seedream":
                task_type = f"{task_type}_{provider}"
        if task_type == "structured_learning_resource":
            from app.services.structured_multimodal_resources import build_structured_resource

            result = build_structured_resource(context)
            return {
                "status": "completed",
                "provider": "local_template",
                "task_type": task_type,
                "tool": "local_structured_template",
                "title": result["title"],
                "content": result["content"],
                "content_url": None,
                "metadata": {"raw_status": "completed", "tool": "local_structured_template"},
                "error_code": None,
                "user_message": _text(context.get("user_message")),
                "warnings": [],
                "result": result,
            }
        tool_name, tool = self.registry.select_tool(task_type)
        if not tool:
            return {
                "status": "generation_failed",
                "provider": "none",
                "task_type": task_type,
                "tool": "",
                "title": task_type.replace("_", " ").title(),
                "content": "",
                "content_url": None,
                "metadata": {"raw_status": "unsupported"},
                "error_code": "unsupported",
                "user_message": _text(context.get("user_message")),
                "warnings": ["当前多模态请求暂不支持。"],
                "result": {},
                "trace": {"input_keys": sorted(context.keys())},
            }

        result = tool.run({**context, "task_type": task_type})
        if not isinstance(result, dict):
            result = {"status": "failed", "provider": tool_name or "unknown", "warnings": ["多模态服务返回了无效结果。"], "result": {}}
        payload = result.get("result") if isinstance(result.get("result"), dict) else result

        # ── deep_solve augmentation: 图片解题 → 提取文字后走分步推理 ──
        _SOLVE_TASKS = {"explain_image_question", "solve_image_question", "image_understanding"}
        if task_type in _SOLVE_TASKS and payload.get("question_text"):
            try:
                from app.services.deeptutor_client import generate_solution
                question_text = str(payload.get("question_text", ""))
                answer = str(payload.get("answer", ""))
                solution = generate_solution(question_text, answer)
                if solution and len(solution) > 30:
                    payload["deep_solve_solution"] = solution
                    if not payload.get("display_text"):
                        payload["display_text"] = solution
                    else:
                        payload["display_text"] = solution + "\n\n---\n📷 图片原文识别：\n" + str(payload.get("display_text", ""))[:300]
            except Exception:
                pass  # deep_solve 失败不影响主流程
        status, error_code = _public_status(result.get("status"))
        content, content_url = _result_content(payload)
        warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        if status == "generation_failed":
            warnings = ["请求的多模态内容生成失败，请检查输入后重试。"]
        elif status == "provider_not_configured":
            warnings = ["所需的多模态服务尚未配置。"]
        return {
            "task_type": task_type,
            "tool": tool_name or "",
            **result,
            "status": status,
            "title": task_type.replace("_", " ").title(),
            "content": content,
            "content_url": content_url,
            "metadata": {"raw_status": _text(result.get("status")), "tool": tool_name or ""},
            "error_code": error_code,
            "user_message": _text(context.get("user_message")),
            "warnings": warnings,
        }


@register_agent
class MultimodalAgentAdapter(BaseAgent):
    """BaseAgent 适配器，让 MultimodalAgent 可以被 AgentFactory 管理和加入 pipeline。"""
    agent_id = "multimodal_agent"
    agent_name = "多模态资源生成智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        inner = MultimodalAgent(getattr(self, '_registry', None))
        mm_result = inner.run(context)
        status = mm_result.get("status", "generation_failed")
        content = mm_result.get("content", "")
        content_url = mm_result.get("content_url", "")
        task_type = mm_result.get("task_type", "")
        if status == "completed" and (content or content_url):
            resources = [{
                "type": "multimodal",
                "title": mm_result.get("title", ""),
                "content": content,
                "content_url": content_url,
                "format": "video" if "video" in task_type else "image",
                "source": "multimodal_agent",
                "multimodal_status": "generated" if content_url else "script_only",
                "quality_status": "passed",
            }]
        else:
            resources = [{
                "type": "multimodal",
                "title": mm_result.get("title", ""),
                "content": content or mm_result.get("user_message", ""),
                "source": "multimodal_agent",
                "multimodal_status": "generation_failed" if status != "completed" else "script_only",
                "quality_status": "fallback",
            }]
        return {"resources": resources, "agent_step": self.agent_step()}
