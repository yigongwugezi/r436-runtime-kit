"""Multimodal worker agent.

This agent plans and executes multimodal tools, then returns structured output.
It does not own final user-visible replies.
"""

from __future__ import annotations

import json
import re
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
    raw_points = []
    for key in ("possible_knowledge_points", "knowledge_points", "target_knowledge_points"):
        raw_points.extend(_as_list(vision.get(key)))
    cleaned = [_text(point) for point in raw_points if _text(point)]
    cleaned.extend(_topic_hints(vision))
    if cleaned:
        return list(dict.fromkeys(cleaned))[:12]
    fallback = _text(vision.get("summary") or vision.get("detected_text") or vision.get("question_text"))
    return [part.strip() for part in fallback.replace("\n", ".").split(".") if part.strip()][:6]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _current_image_supplied(context: dict[str, Any]) -> bool:
    return bool(context.get("attachments") or context.get("image_url") or context.get("image_base64"))


def _question_text(item: dict[str, Any]) -> str:
    return _text(
        item.get("question_text")
        or item.get("stem")
        or item.get("question")
        or item.get("text")
        or item.get("content")
        or item.get("title")
    )


def _topic_hints(vision: dict[str, Any]) -> list[str]:
    text = "\n".join(_text(vision.get(key)) for key in ("detected_text", "question_text", "summary"))
    hints = [
        ("定义域", "函数定义域"),
        ("奇偶", "奇偶函数"),
        ("反函数", "反函数"),
        ("复合函数", "复合函数"),
        ("分段", "分段函数"),
        ("数列", "数列极限"),
        ("无穷小", "无穷小比较"),
        ("等价无穷小", "等价无穷小"),
        ("渐近线", "渐近线"),
    ]
    return [label for needle, label in hints if needle in text]


def _vision_evidence(vision: dict[str, Any], questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    questions = questions if questions is not None else _extract_questions(vision)
    return {
        "summary": _text(vision.get("summary")),
        "subject": _text(vision.get("subject")),
        "detected_text": _text(vision.get("detected_text")),
        "question_text": _text(vision.get("question_text")),
        "knowledge_points": _knowledge_points(vision),
        "questions": questions,
        "answers": _as_list(vision.get("answers") or vision.get("answer")),
        "formulas": _as_list(vision.get("formulas") or vision.get("formula_text")),
    }


def _markdown_node_count(markdown: str) -> int:
    return len([line for line in markdown.splitlines() if line.lstrip().startswith("-")])


def _extract_questions(vision: dict[str, Any]) -> list[dict[str, Any]]:
    questions = vision.get("extracted_questions") or vision.get("questions") or []
    if isinstance(questions, dict):
        questions = [questions]
    result: list[dict[str, Any]] = []
    if isinstance(questions, list):
        for idx, item in enumerate(questions, start=1):
            item = item if isinstance(item, dict) else {"question_text": str(item)}
            text = _question_text(item)
            if not text:
                text = f"第 {idx} 题题干识别不完整"
            try:
                question_index = int(item.get("index") or item.get("question_index") or idx)
            except (TypeError, ValueError):
                question_index = idx
            result.append({
                "index": question_index,
                "question_text": text,
                "options": _as_list(item.get("options") or item.get("choices")),
                "knowledge_points": _as_list(item.get("knowledge_points") or item.get("possible_knowledge_points")),
                "answer": _text(item.get("answer") or item.get("correct_answer")),
                "explanation_steps": _as_list(item.get("explanation_steps") or item.get("solution_steps")),
                "common_mistakes": _as_list(item.get("common_mistakes")),
                "needs_manual_review": bool(item.get("needs_manual_review")),
            })
    if result:
        return result
    question = _text(vision.get("question_text"))
    if not question and "question" in _text(vision.get("image_type")).lower():
        question = _text(vision.get("detected_text"))
    if not question:
        return []
    return [{
        "index": 1,
        "question_text": question,
        "knowledge_points": _knowledge_points(vision),
        "answer": _text(vision.get("answer")),
        "explanation_steps": _as_list(vision.get("explanation_steps") or vision.get("solution_steps")),
        "common_mistakes": _as_list(vision.get("common_mistakes")),
        "needs_manual_review": bool(vision.get("needs_manual_review")),
    }]


def _question_index_from_message(message: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*题", message)
    if match:
        return int(match.group(1))
    cn = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    match = re.search(r"第\s*([一二两三四五六七八九十])\s*题", message)
    return cn.get(match.group(1)) if match else None


def _selected_questions(message: str, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = _question_index_from_message(message)
    if wanted is None:
        return questions
    selected = []
    for item in questions:
        try:
            current = int(item.get("index") or 0)
        except (TypeError, ValueError):
            current = 0
        if current == wanted:
            selected.append(item)
    return selected or questions[:1]


def _review_lines(result: dict[str, Any]) -> list[str]:
    reasons = [_text(item) for item in _as_list(result.get("review_reasons")) if _text(item)]
    fields = [_text(item) for item in _as_list(result.get("uncertain_fields")) if _text(item)]
    indices = [str(item) for item in _as_list(result.get("uncertain_question_indices")) if _text(item)]
    lines = []
    if reasons:
        lines.append("不确定项：" + "；".join(reasons))
    if indices:
        lines.append("涉及题号：" + "、".join(indices))
    if fields:
        lines.append("涉及字段：" + "、".join(fields))
    return lines


def _fallback_explanation_text(questions: list[dict[str, Any]], vision: dict[str, Any]) -> str:
    lines = ["我先按图片里能识别到的信息来讲："]
    for item in questions:
        idx = item.get("index") or 1
        lines.append(f"\n第 {idx} 题")
        lines.append(f"题目：{item.get('question_text')}")
        points = [str(point) for point in _as_list(item.get("knowledge_points")) if _text(point)]
        if points:
            lines.append("知识点：" + "、".join(points))
        if item.get("answer"):
            lines.append(f"答案：{item.get('answer')}")
        steps = [str(step) for step in _as_list(item.get("explanation_steps")) if _text(step)]
        if steps:
            lines.append("讲解：" + "；".join(steps))
        else:
            lines.append("讲解：这道题需要结合题干条件逐步推导；图片里可识别信息有限，我不会强行补不存在的条件。")
        mistakes = [str(step) for step in _as_list(item.get("common_mistakes")) if _text(step)]
        if mistakes:
            lines.append("常见错误：" + "、".join(mistakes))
    lines.extend(_review_lines(vision))
    return "\n".join(lines).strip()


def _fallback_mindmap(vision: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    questions = _extract_questions(vision)
    points = _knowledge_points(vision)
    title = _text(vision.get("summary"))[:50] or _text(context.get("topic")) or "图片知识结构"
    point_children = [{"title": point, "children": []} for point in points]
    if questions:
        children = [
            {
                "title": f"第 {item.get('index')} 题：{_text(item.get('question_text'))[:24]}",
                "children": [{"title": str(point)} for point in (_as_list(item.get("knowledge_points")) or points[:3]) if _text(point)],
            }
            for item in questions
        ]
    else:
        children = point_children
    if point_children:
        children.insert(0, {"title": "核心知识点", "children": point_children[:10]})
    children.append({"title": "常见错误", "children": [{"title": "题干条件看漏"}, {"title": "公式适用条件混淆"}, {"title": "计算步骤跳步"}]})
    mindmap = {"title": title, "children": children or [{"title": "待补充识别结果", "children": []}]}
    return {
        "title": title,
        "root_topic": title,
        "mindmap_json": mindmap,
        "markdown": _json_to_markdown(mindmap),
        "mermaid": _json_to_mermaid(mindmap),
        "nodes_count": len(children) + sum(len(node.get("children") or []) for node in children),
        "vision_result": vision,
    }


def _mindmap_from_markdown(markdown: str) -> dict[str, Any]:
    lines = [line.rstrip() for line in markdown.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else "图片知识结构"
    children: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = [(0, {"title": title, "children": children})]
    for line in lines[1:]:
        stripped = line.lstrip()
        if not stripped.startswith("-"):
            continue
        level = (len(line) - len(stripped)) // 2 + 1
        node = {"title": stripped.lstrip("- ").strip(), "children": []}
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack[-1][1].setdefault("children", []).append(node)
        stack.append((level, node))
    return {"title": title, "children": children}


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
        image_ref_words = ("这张图", "上面这张图", "刚才那张图", "这张图片", "图中", "图片里", "这道题", "这页笔记", "题图", "错题图")
        has_image_ref = _has_any(text, image_ref_words)
        has_image = bool(
            attachments
            or context.get("image_url")
            or context.get("image_base64")
            or context.get("last_vision_result")
            or context.get("last_image_input")
            or has_image_ref
        )

        mindmap_words = ("\u601d\u7ef4\u5bfc\u56fe", "\u8111\u56fe", "\u77e5\u8bc6\u56fe\u8c31", "\u77e5\u8bc6\u56fe", "\u77e5\u8bc6\u7ed3\u6784")
        flashcard_words = ("\u590d\u4e60\u5361\u7247", "\u80cc\u8bf5\u5361", "\u62bd\u8ba4\u5361", "\u8bb0\u5fc6\u5361", "\u5361\u7247")
        explain_words = ("\u8bb2\u4e00\u4e0b", "\u8bb2\u89e3", "\u600e\u4e48\u505a", "\u6279\u6539", "\u89e3\u8fd9", "\u89e3\u7b54", "\u7b54\u6848", "继续讲", "讲第", "只讲")
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

        if _question_index_from_message(user_message or "") is not None and _has_any(text, explain_words):
            return "explain_image_question", "follow-up asks to explain a previous image question"
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
        task_type = str(plan.get("task_type") or "")
        if task_type.startswith("image_") or task_type in {"explain_image_question", "solve_image_question"}:
            cached_vision = context.get("last_vision_result")
            if isinstance(cached_vision, dict) and not _current_image_supplied(context):
                cached_vision = {
                    **cached_vision,
                    "extracted_questions": context.get("last_extracted_questions") or cached_vision.get("extracted_questions") or cached_vision.get("questions") or [],
                }
                executed = {
                    "status": "success",
                    "provider": "session_cache",
                    "result": cached_vision,
                    "warnings": [],
                    "trace": {"source": "last_vision_result", "cache_hit": True},
                }
            else:
                executed = tool.run({**context, "task_type": plan.get("task_type")})
        else:
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
        client = self._get_llm_client()
        result = None
        if client is not None:
            try:
                questions = _extract_questions(vision)
                evidence = _vision_evidence(vision, questions)
                prompt = (
                    "请基于下面图片识别结果生成 Markmap 可渲染的 Markdown 层级脑图。"
                    "至少包含 8 个有意义知识节点，使用两到三级层级。"
                    "只输出 Markdown，不要解释，不要包代码块。\n\n"
                    f"用户请求：{_text(context.get('user_message'))}\n"
                    f"完整图片证据：{json.dumps(evidence, ensure_ascii=False)}"
                )
                markdown = _text(client.chat([
                    {"role": "system", "content": "你是教学内容整理助手，负责把图片题目或笔记整理成清晰脑图。"},
                    {"role": "user", "content": prompt},
                ], temperature=0.2))
                if markdown.startswith("```"):
                    markdown = "\n".join(line for line in markdown.splitlines() if not line.strip().startswith("```")).strip()
                if markdown:
                    if _markdown_node_count(markdown) < 6:
                        raise ValueError("mindmap content too sparse")
                    title = markdown.splitlines()[0].lstrip("# ").strip() or _text(vision.get("summary"))[:50] or "图片知识结构"
                    result = {
                        "title": title,
                        "root_topic": title,
                        "markdown": markdown,
                        "mindmap_json": _mindmap_from_markdown(markdown),
                        "mermaid": "",
                        "nodes_count": max(1, len([line for line in markdown.splitlines() if line.lstrip().startswith("-")])),
                        "vision_result": vision,
                    }
            except Exception as exc:
                executed.setdefault("warnings", []).append(f"LLM mindmap generation failed; used local result: {exc}")
        if result is None:
            result = _fallback_mindmap(vision, context)
        result["needs_manual_review"] = bool(vision.get("needs_manual_review"))
        result["review_reasons"] = vision.get("review_reasons", [])
        result["uncertain_question_indices"] = vision.get("uncertain_question_indices", [])
        result["uncertain_fields"] = vision.get("uncertain_fields", [])
        result["uncertain_spans"] = vision.get("uncertain_spans", [])
        result["review_level"] = vision.get("review_level", "low")
        result["can_continue"] = vision.get("can_continue", True)
        return {
            **executed,
            "status": "needs_manual_review" if result.get("needs_manual_review") else "success",
            "result": result,
            "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "mindmap_generated": True, "llm_stage": client is not None},
        }

    def _image_to_flashcards(self, executed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if executed.get("status") not in {"success", "partial_success"}:
            return executed
        vision = _vision_result(executed)
        client = self._get_llm_client()
        if client is not None:
            try:
                evidence = _vision_evidence(vision)
                raw = client.chat([
                    {"role": "system", "content": "你是中文复习卡片助手，只输出 JSON。"},
                    {
                        "role": "user",
                        "content": (
                            "请基于图片识别结果生成 6-10 张复习卡片。"
                            "只返回 JSON：{\"cards\":[{\"front\":\"问题\",\"back\":\"答案\",\"knowledge_point\":\"知识点\",\"difficulty\":\"basic|medium|hard\",\"card_type\":\"concept|mistake|practice\"}]}。"
                            "内容必须来自识别结果，不要编造。\n\n"
                            f"{json.dumps(evidence, ensure_ascii=False)}"
                        ),
                    },
                ], temperature=0.2)
                parsed = parse_safe(raw)
                cards = parsed.get("cards") if isinstance(parsed.get("cards"), list) else []
                if len(cards) >= 5:
                    return {
                        **executed,
                        "status": "success",
                        "result": {
                            "vision_result": vision,
                            "cards": cards[:10],
                            "needs_manual_review": bool(vision.get("needs_manual_review")),
                            "review_reasons": vision.get("review_reasons", []),
                            "uncertain_question_indices": vision.get("uncertain_question_indices", []),
                            "uncertain_fields": vision.get("uncertain_fields", []),
                            "uncertain_spans": vision.get("uncertain_spans", []),
                            "review_level": vision.get("review_level", "low"),
                            "can_continue": vision.get("can_continue", True),
                        },
                        "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "flashcards_generated": True, "llm_stage": True},
                    }
            except Exception as exc:
                executed.setdefault("warnings", []).append(f"LLM flashcard generation failed; used local result: {exc}")
        if isinstance(vision.get("cards"), list) and len(vision.get("cards") or []) >= 5:
            return {**executed, "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "flashcards_generated": True, "llm_stage": False}}
        questions = _extract_questions(vision)
        points = _knowledge_points(vision)
        cards = []
        for item in questions[:5]:
            text = _text(item.get("question_text"))
            point = _text((_as_list(item.get("knowledge_points")) or points or ["题图复习"])[0])
            cards.append({
                "front": f"第 {item.get('index')} 题考什么？",
                "back": text[:280] or "题干识别不完整，建议重新上传更清晰图片。",
                "knowledge_point": point,
                "difficulty": "medium",
                "card_type": "practice",
                "source_evidence": text,
            })
        for point in points:
            if len(cards) >= 10:
                break
            cards.append({
                "front": f"{point} 的关键点是什么？",
                "back": _text(vision.get("summary") or vision.get("detected_text"))[:300] or "Review this point from the image.",
                "knowledge_point": point,
                "difficulty": "medium",
                "card_type": "concept",
            })
        while len(cards) < 5:
            cards.append({
                "front": f"第 {len(cards) + 1} 个待确认复习点是什么？",
                "back": _text(vision.get("summary") or vision.get("detected_text"))[:300] or "图片信息不足，建议重新上传更清晰图片。",
                "knowledge_point": "题图复习",
                "difficulty": "basic",
                "card_type": "review",
            })
        return {
            **executed,
            "status": "success",
            "result": {
                "vision_result": vision,
                "cards": cards[:10],
                "needs_manual_review": bool(vision.get("needs_manual_review")),
                "review_reasons": vision.get("review_reasons", []),
                "uncertain_question_indices": vision.get("uncertain_question_indices", []),
                "uncertain_fields": vision.get("uncertain_fields", []),
                "uncertain_spans": vision.get("uncertain_spans", []),
                "review_level": vision.get("review_level", "low"),
                "can_continue": vision.get("can_continue", True),
            },
            "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "flashcards_generated": True, "llm_stage": False},
        }

    def _explain_image_question(self, executed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if executed.get("status") not in {"success", "partial_success"}:
            return executed
        vision = _vision_result(executed)
        questions = _selected_questions(_text(context.get("user_message")), _extract_questions(vision))
        if not questions:
            return {
                **executed,
                "status": "needs_manual_review",
                "result": {
                    "vision_result": vision,
                    "needs_manual_review": True,
                    "review_reasons": ["OCR 关键信息缺失"],
                    "uncertain_question_indices": [],
                    "uncertain_fields": ["question_text"],
                    "uncertain_spans": [],
                    "review_level": "high",
                    "can_continue": False,
                },
                "warnings": [*executed.get("warnings", []), "question text was not recognized clearly"],
            }
        result = {
            "vision_result": vision,
            "extracted_questions": questions,
            "selected_question_indices": [item.get("index") for item in questions],
            "question_text": "\n".join(str(item.get("question_text")) for item in questions),
            "chat_text": _fallback_explanation_text(questions, vision),
            "display_text": "",
            "teaching_text": "",
            "answer": "",
            "knowledge_points": list(dict.fromkeys(
                str(point)
                for item in questions
                for point in _as_list(item.get("knowledge_points"))
                if _text(point)
            )) or _knowledge_points(vision),
            "common_mistakes": [],
            "needs_manual_review": bool(vision.get("needs_manual_review")),
            "review_reasons": vision.get("review_reasons", []),
            "uncertain_question_indices": vision.get("uncertain_question_indices", []),
            "uncertain_fields": vision.get("uncertain_fields", []),
            "uncertain_spans": vision.get("uncertain_spans", []),
            "review_level": vision.get("review_level", "low"),
            "can_continue": vision.get("can_continue", True),
        }
        client = self._get_llm_client()
        if client:
            try:
                prompt = (
                    "请把图片里的题目讲成普通聊天回答，不要输出大块 JSON，不要写成文档卡片。"
                    "如果用户没有指定题号，先说明识别到几道题，列出每题考点概览，并详细讲第 1 题和第 2 题。"
                    "如果用户指定第几题，只讲对应题。"
                    "讲解包含：题目概述、知识点、解题步骤、答案、常见错误、不确定项。"
                    "最后提示用户可以说“继续讲第3题”。\n\n"
                    f"用户请求：{_text(context.get('user_message'))}\n"
                    f"完整图片证据：{json.dumps(_vision_evidence(vision, questions), ensure_ascii=False)}"
                )
                raw = client.chat([
                    {"role": "system", "content": "你是耐心的中文教学助教，只输出自然的聊天文本。"},
                    {"role": "user", "content": prompt},
                ], temperature=0.2)
                text = _text(raw)
                if text.startswith("{"):
                    parsed = parse_safe(text)
                    result["chat_text"] = _text(parsed.get("chat_text") or parsed.get("content")) or result["chat_text"]
                    if isinstance(parsed.get("questions"), list):
                        result["explained_questions"] = parsed["questions"]
                    if parsed.get("answer"):
                        result["answer"] = _text(parsed.get("answer"))
                    if parsed.get("common_mistakes"):
                        result["common_mistakes"] = _as_list(parsed.get("common_mistakes"))
                elif text:
                    result["chat_text"] = text
            except Exception as exc:
                executed.setdefault("warnings", []).append(f"LLM explanation failed: {exc}")
        result["display_text"] = result["chat_text"]
        result["teaching_text"] = result["chat_text"]
        return {
            **executed,
            "status": "success" if not result.get("needs_manual_review") else "needs_manual_review",
            "result": result,
            "trace": {**executed.get("trace", {}), "vision_status": executed.get("status"), "question_explained": True, "llm_stage": client is not None},
        }

    def _workflow_trace(self, plan: dict[str, Any], executed: dict[str, Any]) -> dict[str, Any]:
        status = str(executed.get("status") or "failed")
        workflow_status = "success" if status == "success" else ("partial" if status in {"partial_success", "needs_input", "needs_manual_review", "provider_not_configured", "script_ready_provider_not_configured", "unsupported"} else "failed")
        warnings = executed.get("warnings", []) if isinstance(executed.get("warnings"), list) else []
        task_type = str(plan.get("task_type") or "execute")
        trace = executed.get("trace") if isinstance(executed.get("trace"), dict) else {}
        llm_stage = bool(trace.get("llm_stage"))
        provider = str(executed.get("provider") or "")
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
            "vision_extract_by_qwen_vl": (task_type.startswith("image_") or task_type in {"explain_image_question", "solve_image_question"}) and provider != "session_cache",
            "vision_context_reused": provider == "session_cache",
            "teaching_generation_by_main_llm": task_type in {"explain_image_question", "solve_image_question"} and llm_stage,
            "mindmap_generation_by_main_llm": task_type == "image_to_mindmap" and llm_stage,
            "flashcard_generation_by_main_llm": task_type == "image_to_flashcards" and llm_stage,
            "variant_generation_by_main_llm": task_type == "image_to_variant_questions" and llm_stage,
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
