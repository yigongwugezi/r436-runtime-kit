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


def _json_to_markdown(mindmap: dict[str, Any]) -> str:
    lines = [f"# {_text(mindmap.get('title')) or 'Mind Map'}"]

    def walk(nodes: Any, depth: int) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            lines.append(f"{'  ' * depth}- {_text(node.get('title')) or 'Untitled'}")
            walk(node.get("children"), depth + 1)

    walk(mindmap.get("children"), 0)
    return "\n".join(lines)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _vision_result(executed: dict[str, Any]) -> dict[str, Any]:
    result = executed.get("result")
    return result if isinstance(result, dict) else {}


def _knowledge_points(vision: dict[str, Any]) -> list[str]:
    points = vision.get("possible_knowledge_points")
    if isinstance(points, list):
        cleaned = [_text(point) for point in points if _text(point)]
        if cleaned:
            return cleaned[:8]
    fallback = _text(vision.get("summary") or vision.get("detected_text") or vision.get("question_text"))
    return [part.strip() for part in fallback.replace("\n", ".").split(".") if part.strip()][:6]


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
        context = context or {}
        has_image = bool(attachments or context.get("image_url") or context.get("image_base64"))

        mindmap_words = ("\u601d\u7ef4\u5bfc\u56fe", "\u8111\u56fe", "\u77e5\u8bc6\u56fe\u8c31", "\u77e5\u8bc6\u56fe", "\u77e5\u8bc6\u7ed3\u6784")
        flashcard_words = ("\u590d\u4e60\u5361\u7247", "\u80cc\u8bf5\u5361", "\u62bd\u8ba4\u5361", "\u8bb0\u5fc6\u5361", "\u5361\u7247")
        explain_words = ("\u8bb2\u4e00\u4e0b", "\u8bb2\u89e3", "\u600e\u4e48\u505a", "\u6279\u6539", "\u89e3\u8fd9", "\u89e3\u7b54", "\u7b54\u6848")
        wrong_words = ("\u9519\u9898", "\u9519\u56e0", "\u9519\u54ea", "\u8584\u5f31\u70b9", "\u5f31\u70b9")
        note_words = ("\u7b14\u8bb0", "\u8bfe\u4ef6", "\u6559\u6750", "\u8bb2\u4e49", "\u603b\u7ed3", "\u6574\u7406", "\u63d0\u70bc")
        plan_words = ("\u5b66\u4e60\u8ba1\u5212", "\u600e\u4e48\u5b66", "\u5b89\u6392", "\u8def\u5f84", "\u89c4\u5212")
        variant_words = ("\u53d8\u5f0f\u9898", "\u7c7b\u4f3c\u9898", "\u4e3e\u4e00\u53cd\u4e09", "\u518d\u51fa\u51e0\u9053")
        bundle_words = ("\u4e00\u952e\u6574\u7406", "\u5b66\u4e60\u8d44\u6599", "\u8d44\u6e90\u5305", "\u5b66\u4e60\u5305", "\u5b8c\u6574")
        vision_words = ("\u8bc6\u522b", "\u770b\u770b", "\u8fd9\u662f\u4ec0\u4e48", "\u5206\u6790\u8fd9\u5f20\u56fe", "\u9898\u56fe", "\u56fe\u7247", "\u622a\u56fe", "\u63d0\u53d6\u77e5\u8bc6\u70b9")
        image_words = ("\u751f\u6210\u4e00\u5f20", "\u751f\u6210\u56fe\u7247", "\u753b\u56fe", "\u6559\u5b66\u56fe", "\u6982\u5ff5\u56fe", "\u77e5\u8bc6\u5361\u7247")
        video_words = ("\u751f\u6210\u89c6\u9891", "\u8bb2\u89e3\u89c6\u9891", "\u5fae\u8bfe\u89c6\u9891", "\u52a8\u753b")
        script_words = ("\u5206\u955c\u811a\u672c", "\u5fae\u8bfe\u811a\u672c")

        if has_image:
            matches = [
                _has_any(text, mindmap_words),
                _has_any(text, flashcard_words),
                _has_any(text, explain_words),
                _has_any(text, wrong_words),
                _has_any(text, note_words),
                _has_any(text, plan_words),
                _has_any(text, variant_words),
            ]
            if _has_any(text, bundle_words) or sum(1 for item in matches if item) > 1:
                return "image_to_resource_bundle", "image input asks for a resource bundle"
            if matches[0]:
                return "image_to_mindmap", "image input asks for a mind map"
            if matches[1]:
                return "image_to_flashcards", "image input asks for flashcards"
            if matches[2]:
                return "explain_image_question", "image input asks for question explanation"
            if matches[3]:
                return "image_wrong_question_analysis", "image input asks for wrong-question analysis"
            if matches[4]:
                return "image_note_summary", "image input asks for note summary"
            if matches[5]:
                return "image_to_learning_plan", "image input asks for learning plan"
            if matches[6]:
                return "image_to_variant_questions", "image input asks for variant questions"
        if has_image or (_has_any(text, vision_words) and not _has_any(text, image_words)):
            return "image_understanding", "message or attachments ask for image understanding"
        if _has_any(text, mindmap_words):
            return "mindmap_generation", "message asks for a mind map or knowledge graph"
        if _has_any(text, script_words):
            return "video_script_generation", "message asks for a video script"
        if _has_any(text, video_words):
            return "video_generation", "message asks for a generated video"
        if _has_any(text, image_words):
            if "\u77e5\u8bc6\u5361\u7247" in text:
                return "concept_card_generation", "message asks for a generated concept card"
            if "\u6559\u5b66\u56fe" in text or "\u8bb2\u89e3\u56fe" in text:
                return "teaching_diagram_generation", "message asks for a teaching diagram"
            return "image_generation", "message asks for a generated image"

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
        executed = tool.run({**context, "task_type": plan.get("task_type")})
        if plan.get("task_type") == "mindmap_generation" and executed.get("status") == "success":
            return self._enhance_mindmap_with_llm(executed, context)
        if plan.get("task_type") in {"image_to_mindmap", "note_image_to_mindmap", "question_image_to_mindmap"}:
            return self._image_to_mindmap(executed, context)
        if plan.get("task_type") in {"image_to_flashcards", "note_image_to_flashcards", "question_image_to_flashcards"}:
            return self._image_to_flashcards(executed, context)
        if plan.get("task_type") in {"explain_image_question", "solve_image_question"}:
            return self._explain_image_question(executed, context)
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

    def _image_to_mindmap(self, executed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if executed.get("status") not in {"success", "partial_success"}:
            return executed
        vision = _vision_result(executed)
        if vision.get("markdown") or vision.get("mindmap_json"):
            return {**executed, "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "mindmap_generated": True}}
        points = _knowledge_points(vision)
        title = _text(vision.get("summary"))[:50] or _text(context.get("topic")) or "Image knowledge"
        children = [{"title": point, "children": []} for point in points] or [{"title": "Needs manual review", "children": []}]
        mindmap = {"title": title, "children": children}
        return {
            **executed,
            "status": "success" if points else "needs_manual_review",
            "result": {
                "vision_result": vision,
                "mindmap_json": mindmap,
                "markdown": _json_to_markdown(mindmap),
                "mermaid": _json_to_mermaid(mindmap),
            },
            "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "mindmap_generated": True},
        }

    def _image_to_flashcards(self, executed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if executed.get("status") not in {"success", "partial_success"}:
            return executed
        vision = _vision_result(executed)
        if isinstance(vision.get("cards"), list):
            return {**executed, "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "flashcards_generated": True}}
        points = _knowledge_points(vision)
        cards = []
        for point in (points or [_text(vision.get("summary")) or "Image content"])[:6]:
            cards.append({
                "front": point,
                "back": _text(vision.get("summary") or vision.get("detected_text"))[:300] or "Review this point from the image.",
                "knowledge_point": point,
                "difficulty": "medium",
            })
        while len(cards) < 3:
            cards.append({
                "front": f"Review point {len(cards) + 1}",
                "back": _text(vision.get("summary")) or "Needs manual review.",
                "knowledge_point": "image_review",
                "difficulty": "basic",
            })
        return {
            **executed,
            "status": "success",
            "result": {"vision_result": vision, "cards": cards[:6]},
            "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "flashcards_generated": True},
        }

    def _explain_image_question(self, executed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if executed.get("status") not in {"success", "partial_success"}:
            return executed
        vision = _vision_result(executed)
        if vision.get("explanation_steps") or vision.get("answer"):
            return {**executed, "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "question_explained": True}}
        question = _text(vision.get("question_text") or vision.get("detected_text"))
        if not question:
            return {
                **executed,
                "status": "needs_manual_review",
                "result": {"vision_result": vision, "needs_manual_review": True},
                "warnings": [*executed.get("warnings", []), "question text was not recognized clearly"],
            }
        result = {
            "vision_result": vision,
            "question_text": question,
            "analysis": "The question was recognized. Configure a text LLM provider for full step-by-step solving.",
            "solution_steps": [],
            "answer": "",
            "knowledge_points": _knowledge_points(vision),
            "common_mistakes": [],
            "needs_manual_review": True,
        }
        client = self._get_llm_client()
        if client:
            try:
                raw = client.chat([
                    {"role": "system", "content": "Return JSON with analysis, solution_steps, answer, knowledge_points, common_mistakes."},
                    {"role": "user", "content": question},
                ], temperature=0.2)
                parsed = parse_safe(raw)
                result.update({k: parsed.get(k, result.get(k)) for k in result.keys() if k in parsed})
                result["needs_manual_review"] = False
            except Exception as exc:
                executed.setdefault("warnings", []).append(f"LLM explanation failed: {exc}")
        return {
            **executed,
            "status": "success" if not result.get("needs_manual_review") else "needs_manual_review",
            "result": result,
            "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "question_explained": True},
        }

    def _workflow_trace(self, plan: dict[str, Any], executed: dict[str, Any]) -> dict[str, Any]:
        status = str(executed.get("status") or "failed")
        workflow_status = "success" if status == "success" else ("partial" if status in {"partial_success", "needs_input", "needs_manual_review", "provider_not_configured", "script_ready_provider_not_configured", "unsupported"} else "failed")
        warnings = executed.get("warnings", []) if isinstance(executed.get("warnings"), list) else []
        task_type = str(plan.get("task_type") or "execute")
        task_steps = {
            "image_understanding": ["understand_image"],
            "explain_image_question": ["understand_image", "generate_explanation"],
            "solve_image_question": ["understand_image", "generate_explanation"],
            "image_wrong_question_analysis": ["understand_image", "analyze_wrong_question"],
            "image_note_summary": ["understand_image", "generate_note_summary"],
            "image_to_mindmap": ["understand_image", "generate_mindmap"],
            "image_to_flashcards": ["understand_image", "generate_flashcards"],
            "image_to_learning_plan": ["understand_image", "generate_learning_plan"],
            "image_to_variant_questions": ["understand_image", "generate_variants"],
            "image_to_resource_bundle": [
                "understand_image",
                "generate_explanation",
                "analyze_wrong_question",
                "generate_note_summary",
                "generate_mindmap",
                "generate_flashcards",
                "generate_learning_plan",
                "generate_variants",
                "build_resource_bundle",
                "prepare_resource_candidate",
                "prepare_knowledge_candidates",
            ],
        }.get(task_type, [task_type])
        steps = [
            {"step": "classify_image_task", "agent": self.name, "status": "success", "summary": task_type, "warnings": []},
        ]
        for step in task_steps:
            if step == "understand_image":
                steps.append({
                    "step": "vision_understanding",
                    "agent": "QwenVisionProvider",
                    "status": status,
                    "summary": f"{task_type} -> {status}",
                    "warnings": warnings,
                })
            steps.append({
                "step": step,
                "agent": str(plan.get("tool") or self.name),
                "status": status,
                "summary": f"{task_type} -> {status}",
                "warnings": warnings,
            })
        return {
            "workflow_name": "multimodal_generation",
            "workflow_status": workflow_status,
            "pipeline_executed": True,
            "steps": steps,
        }

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
                "status": "completed" if status in {"success", "partial_success", "needs_input", "needs_manual_review", "provider_not_configured", "script_ready_provider_not_configured", "unsupported"} else "failed",
                "summary": f"{plan.get('task_type')} -> {status}",
            },
            "workflow_trace": self._workflow_trace(plan, executed),
        }

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        message = str(context.get("user_message") or context.get("message") or "")
        attachments = context.get("attachments") or []
        task_type, reason = self.classify_task(message, attachments, context)
        plan = self.plan(task_type, context, reason)
        executed = self.execute(plan, context)
        return self.summarize(plan, executed)
