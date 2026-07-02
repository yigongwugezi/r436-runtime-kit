"""Multimodal worker agent.

This agent plans and executes multimodal tools, then returns structured output.
It does not own final user-visible replies.
"""

from __future__ import annotations

from typing import Any

from app.services.multimodal_registry import ToolRegistry, default_registry


class MultimodalAgent:
    name = "MultimodalAgent"
    agent_id = "multimodal_agent"
    agent_name = "MultimodalAgent"

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry()

    def classify_task(
        self,
        user_message: str,
        attachments: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        text = (user_message or "").lower()
        attachments = attachments or []

        if any(word in text for word in ("思维导图", "知识图谱", "知识图")):
            return "mindmap_generation", "message asks for a mind map or knowledge graph"
        if any(word in text for word in ("生成视频", "讲解视频", "微课视频")):
            return "video_generation", "message asks for a generated video"
        if any(word in text for word in ("生成一张", "知识卡片", "讲解图", "生成图片", "画图")):
            return "image_generation", "message asks for a generated image"
        if attachments or any(word in text for word in ("识别这张图片", "看看这张题图", "题图", "图片识别")):
            return "image_understanding", "message or attachments ask for image understanding"
        return "multimodal_unknown", "no supported multimodal task matched"

    def plan(self, task_type: str, context: dict[str, Any], reason: str) -> dict[str, Any]:
        tool_name, _tool = self.registry.select_tool(task_type)
        return {
            "task_type": task_type,
            "tool": tool_name,
            "planned_steps": ["classify_task", "select_tool", "execute_tool", "summarize"],
            "reason": reason,
        }

    def execute(self, plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        tool_name = plan.get("tool")
        if not tool_name:
            return {
                "status": "unsupported",
                "provider": "",
                "result": None,
                "warnings": ["暂不支持这个多模态任务。"],
                "trace": {"task_type": plan.get("task_type")},
            }
        tool = self.registry.get_tool(str(tool_name))
        if tool is None:
            return {
                "status": "failed",
                "provider": "",
                "result": None,
                "warnings": [f"Tool not registered: {tool_name}"],
                "trace": {"tool": tool_name},
            }
        return tool.run(context)

    def summarize(self, plan: dict[str, Any], executed: dict[str, Any]) -> dict[str, Any]:
        status = str(executed.get("status") or "failed")
        return {
            "agent": self.name,
            "status": status,
            "task_type": plan.get("task_type"),
            "tool": plan.get("tool"),
            "provider": executed.get("provider", ""),
            "result": executed.get("result"),
            "warnings": executed.get("warnings", []),
            "trace": {
                "planned_steps": plan.get("planned_steps", []),
                "selected_tool": plan.get("tool"),
                "reason": plan.get("reason", ""),
                "tool_trace": executed.get("trace", {}),
            },
            "agent_step": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": "completed" if status in {"success", "needs_input", "provider_not_configured", "unsupported"} else "failed",
                "summary": f"{plan.get('task_type')} -> {status}",
            },
        }

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        message = str(context.get("user_message") or context.get("message") or "")
        attachments = context.get("attachments") or []
        task_type, reason = self.classify_task(message, attachments, context)
        plan = self.plan(task_type, context, reason)
        executed = self.execute(plan, context)
        return self.summarize(plan, executed)
