"""Multimodal worker agent.

This agent plans and executes multimodal tools, then returns structured output.
It does not own final user-visible replies.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.services.llm_client import BaseLLMClient, get_llm_client
from app.services.multimodal_registry import ToolRegistry, default_registry
from app.utils.llm_json import parse_safe


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mermaid_label(value: Any) -> str:
    return _text(value).replace("(", " ").replace(")", " ")[:80] or "未命名"


def _json_to_mermaid(mindmap: dict[str, Any]) -> str:
    lines = ["mindmap", f"  root(({_mermaid_label(mindmap.get('title'))}))"]

    def walk(nodes: Any, depth: int) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            lines.append(f"{'  ' * depth}{_mermaid_label(node.get('title'))}")
            walk(node.get("children"), depth + 1)

    walk(mindmap.get("children"), 2)
    return "\n".join(lines)


class MultimodalAgent:
    name = "MultimodalAgent"
    agent_id = "multimodal_agent"
    agent_name = "MultimodalAgent"

    def __init__(self, registry: ToolRegistry | None = None, llm_client: BaseLLMClient | None = None) -> None:
        self.registry = registry or default_registry()
        self.llm_client = llm_client

    def _get_llm_client(self) -> BaseLLMClient | None:
        if self.llm_client is not None:
            return self.llm_client
        if settings.llm_provider == "mock":
            return None
        try:
            return get_llm_client(settings.llm_provider)
        except Exception:
            return None

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
        executed = tool.run(context)
        if plan.get("task_type") == "mindmap_generation" and executed.get("status") == "success":
            return self._enhance_mindmap_with_llm(executed, context)
        return executed

    def _enhance_mindmap_with_llm(self, executed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        client = self._get_llm_client()
        if client is None:
            executed.setdefault("trace", {})["llm_enhanced"] = False
            return executed

        result = executed.get("result") if isinstance(executed.get("result"), dict) else {}
        prompt = (
            "请把下面的学习路径整理成更清晰的思维导图 JSON。"
            "只返回 JSON，不要 markdown。格式："
            '{"title":"课程名","children":[{"title":"阶段","children":[{"title":"知识点"}]}]}。'
            "内容必须来自输入，不要编造不存在的课程。\n\n"
            f"用户请求：{_text(context.get('user_message'))}\n"
            f"上下文：{json.dumps(result, ensure_ascii=False)}"
        )
        try:
            raw = client.chat([
                {"role": "system", "content": "你是学习路径可视化助手，只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ], temperature=0.2)
            mindmap = parse_safe(raw)
            if not isinstance(mindmap.get("children"), list):
                raise ValueError("mindmap children must be a list")
            executed["provider"] = f"{executed.get('provider')}_llm"
            executed["result"] = {
                **result,
                "mindmap_json": mindmap,
                "mermaid": _json_to_mermaid(mindmap),
                "llm_enhanced": True,
            }
            executed.setdefault("trace", {})["llm_enhanced"] = True
            executed["trace"]["llm_provider"] = settings.llm_provider if self.llm_client is None else "injected"
        except Exception as exc:
            executed.setdefault("warnings", []).append(f"LLM mindmap enhancement failed; used local result: {exc}")
            executed.setdefault("trace", {})["llm_enhanced"] = False
        return executed

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
