"""Executable multimodal tools and providers.

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


# Real HTTP providers and upload helpers.
import base64
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.utils.llm_json import parse_safe


UPLOAD_ROOT = settings.project_root / "uploads" / "multimodal"
ALLOWED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class HttpClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        response_body_preview: str = "",
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.response_body_preview = response_body_preview


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _json_post(url: str, payload: dict[str, Any], api_key: str, timeout: int = 60) -> dict[str, Any]:
    response = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        preview = response.text[:300]
        raise HttpClientError(
            f"HTTP {response.status_code}: {preview}",
            http_status=response.status_code,
            response_body_preview=preview,
        )
    return response.json()


def _qwen_chat_endpoint(base_url: str) -> str:
    endpoint = _text(base_url)
    if not endpoint.endswith("/chat/completions"):
        endpoint = urljoin(endpoint.rstrip("/") + "/", "chat/completions")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid Qwen base URL: {base_url}")
    return endpoint


def _data_url_from_base64(value: str) -> str:
    value = _text(value)
    if value.startswith("data:image/"):
        return value
    return f"data:image/png;base64,{value}"


def _is_remote_or_data_image(value: str) -> bool:
    lowered = _text(value).lower()
    return lowered.startswith(("http://", "https://", "data:image/"))


def _local_file_data_url(local_path: str) -> tuple[str, str, str]:
    local_path = _text(local_path)
    if not local_path:
        return "", "missing local image path", "missing"
    local = _resolve_upload_path(local_path)
    if not local or not local.exists():
        return "", f"local image file not found: {local_path}", "missing"
    mime = mimetypes.guess_type(local.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(local.read_bytes()).decode('ascii')}", "", "local_file"


def _resolve_upload_path(local_path: str) -> Path | None:
    if not local_path:
        return None
    candidate = Path(local_path)
    if not candidate.is_absolute():
        candidate = settings.project_root / candidate
    try:
        resolved = candidate.resolve()
        root = UPLOAD_ROOT.resolve()
        if root == resolved or root in resolved.parents:
            return resolved
    except Exception:
        return None
    return None


def image_input_from_context(context: dict[str, Any]) -> tuple[str, str, str]:
    image_url = _text(context.get("image_url"))
    if image_url:
        if _is_remote_or_data_image(image_url):
            return image_url, "", "data_url" if image_url.lower().startswith("data:image/") else "public_url"
        return _local_file_data_url(image_url)

    image_base64 = _text(context.get("image_base64"))
    if image_base64:
        return _data_url_from_base64(image_base64), "", "data_url" if image_base64.lower().startswith("data:image/") else "raw_base64"

    warning = ""
    kind = "missing"
    for item in context.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        if _text(item.get("image_base64")):
            value = _text(item.get("image_base64"))
            return _data_url_from_base64(value), "", "data_url" if value.lower().startswith("data:image/") else "raw_base64"
        if _text(item.get("local_path")):
            data_url, warning, kind = _local_file_data_url(_text(item.get("local_path")))
            if data_url:
                return data_url, "", kind
        for key in ("image_url", "url"):
            url = _text(item.get(key))
            if not url:
                continue
            if _is_remote_or_data_image(url):
                return url, "", "data_url" if url.lower().startswith("data:image/") else "public_url"
            data_url, warning, kind = _local_file_data_url(url)
            if data_url:
                return data_url, "", kind
    return "", warning, kind


def save_multimodal_upload(
    data: bytes,
    *,
    filename: str = "",
    content_type: str = "",
    session_id: str = "anonymous",
) -> dict[str, Any]:
    if not data:
        raise ValueError("empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds 10MB")
    mime = (content_type or mimetypes.guess_type(filename)[0] or "").lower()
    ext = ALLOWED_IMAGE_TYPES.get(mime)
    if not ext:
        suffix = Path(filename or "").suffix.lower().lstrip(".")
        if suffix in {"png", "jpg", "jpeg", "webp"}:
            ext = "jpg" if suffix == "jpeg" else suffix
            mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
    if not ext:
        raise ValueError("only png, jpg, jpeg and webp images are allowed")

    safe_session = re.sub(r"[^a-zA-Z0-9_-]+", "_", _text(session_id) or "anonymous")[:80]
    upload_dir = UPLOAD_ROOT / safe_session
    upload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    path = upload_dir / name
    path.write_bytes(data)
    file_id = f"{safe_session}/{name}"
    return {
        "status": "success",
        "file_id": file_id,
        "url": f"/api/multimodal/file/{file_id}",
        "image_url": f"/api/multimodal/file/{file_id}",
        "local_path": str(path.relative_to(settings.project_root)).replace("\\", "/"),
        "mime_type": mime,
        "size": len(data),
    }


def _normalize_vision_result(parsed: dict[str, Any], raw_text: str) -> dict[str, Any]:
    confidence = _confidence(parsed.get("confidence"), 0.5)
    detected = _text(parsed.get("detected_text"))
    review = _review_metadata(parsed, confidence, detected, parsed.get("summary"), parsed.get("question_text"))
    return {
        "image_type": _friendly_value(parsed.get("image_type")),
        "subject": _friendly_value(parsed.get("subject")),
        "detected_text": detected,
        "question_text": _text(parsed.get("question_text")),
        "student_answer": _text(parsed.get("student_answer")),
        "formula_text": _text(parsed.get("formula_text")),
        "diagram_description": _text(parsed.get("diagram_description")),
        "possible_knowledge_points": _as_list(parsed.get("possible_knowledge_points")),
        "extracted_questions": _as_list(parsed.get("extracted_questions") or parsed.get("questions")),
        "summary": _safe_summary(parsed, raw_text),
        "confidence": confidence,
        **review,
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str):
        parts = re.split(r"[\n,，;；、]+", value)
        return [part.strip() for part in parts if part.strip()]
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _confidence(value: Any, default: float = 0.5) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def _friendly_value(value: Any) -> str:
    text = _text(value)
    if text.lower() in {"unknown", "none", "null", "n/a", "na"}:
        return ""
    if text in {"未知", "无", "暂无", "未识别"}:
        return ""
    return text


def _safe_summary(parsed: dict[str, Any], raw_text: str) -> str:
    summary = _text(parsed.get("summary"))
    if summary:
        return summary
    for key in ("detected_text", "question_text", "diagram_description"):
        value = _text(parsed.get(key))
        if value:
            return value[:500]
    raw = _text(raw_text)
    if raw.startswith("{") or raw.startswith("["):
        return ""
    return raw[:500]


def _review_metadata(parsed: dict[str, Any], confidence: float, *evidence: Any) -> dict[str, Any]:
    reasons = [_text(item) for item in _as_list(parsed.get("review_reasons")) if _text(item)]
    fields = [_text(item) for item in _as_list(parsed.get("uncertain_fields")) if _text(item)]
    indices: list[int] = []
    for item in _as_list(parsed.get("uncertain_question_indices")):
        try:
            indices.append(int(item))
        except (TypeError, ValueError):
            continue

    blob = " ".join([_text(value) for value in evidence] + [_text(parsed.get("uncertainty")), _text(parsed.get("notes"))])
    uncertainty_words = (
        "uncertain", "not clear", "unclear", "truncated", "incomplete", "low confidence",
        "不确定", "不清晰", "看不清", "截断", "不完整", "置信度不足", "无法确认",
    )
    if parsed.get("needs_manual_review") is True and not reasons:
        reasons.append("模型标记识别结果不确定")
    if parsed.get("confidence") not in (None, "") and confidence < 0.55:
        reasons.append("识别置信度偏低")
    if not any(len(_text(item)) >= 8 for item in evidence):
        reasons.append("OCR 关键信息缺失")
        if "detected_text" not in fields:
            fields.append("detected_text")
    if any(word in blob for word in uncertainty_words):
        reasons.append("图片内容存在不清晰或不完整信息")

    return {
        "needs_manual_review": bool(reasons or fields or indices),
        "review_reasons": list(dict.fromkeys(reasons)),
        "uncertain_question_indices": list(dict.fromkeys(indices)),
        "uncertain_fields": list(dict.fromkeys(fields)),
    }


def _ensure_review_fields(result: dict[str, Any], parsed: dict[str, Any], *evidence: Any) -> dict[str, Any]:
    confidence = _confidence(result.get("confidence") or parsed.get("confidence"), 0.5)
    review = _review_metadata(parsed, confidence, *evidence)
    if result.get("needs_manual_review") is True and not review["review_reasons"]:
        review["review_reasons"] = ["模型标记识别结果不确定"]
    result["needs_manual_review"] = bool(result.get("needs_manual_review") or review["needs_manual_review"])
    result["review_reasons"] = list(dict.fromkeys(_as_list(result.get("review_reasons")) + review["review_reasons"]))
    result["uncertain_question_indices"] = list(dict.fromkeys(_as_list(result.get("uncertain_question_indices")) + review["uncertain_question_indices"]))
    result["uncertain_fields"] = list(dict.fromkeys(_as_list(result.get("uncertain_fields")) + review["uncertain_fields"]))
    return result


def _int(value: Any, default: int = 30) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else default


def _needs_review(parsed: dict[str, Any], confidence: float, *evidence: Any) -> bool:
    return _review_metadata(parsed, confidence, *evidence)["needs_manual_review"]


def _cards(value: Any, vision: dict[str, Any]) -> list[dict[str, Any]]:
    items = _as_list(value)
    cards: list[dict[str, Any]] = []
    for item in items:
        item = _as_dict(item)
        front = _text(item.get("front") or item.get("question") or item.get("knowledge_point"))
        back = _text(item.get("back") or item.get("answer") or vision.get("summary"))
        if front and back:
            cards.append({
                "front": front,
                "back": back,
                "knowledge_point": _text(item.get("knowledge_point")) or front,
                "difficulty": _text(item.get("difficulty")) or "medium",
                "card_type": _text(item.get("card_type")) or "concept",
                "source_evidence": _text(item.get("source_evidence")) or _text(vision.get("detected_text") or vision.get("summary")),
            })
    return cards[:10]


def _variants(value: Any) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for item in _as_list(value):
        item = _as_dict(item)
        question = _text(item.get("question"))
        if question:
            variants.append({
                "question": question,
                "answer": _text(item.get("answer")),
                "explanation": _text(item.get("explanation")),
                "difficulty": _text(item.get("difficulty")) or "medium",
                "variation_type": _text(item.get("variation_type")) or "same_knowledge_point",
            })
    return variants[:8]


def _recommended_path(value: Any) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    for item in _as_list(value):
        item = _as_dict(item)
        title = _text(item.get("stage_title") or item.get("title"))
        if title:
            path.append({
                "stage_title": title,
                "objective": _text(item.get("objective") or item.get("goal")),
                "knowledge_points": _as_list(item.get("knowledge_points")),
                "estimated_minutes": _int(item.get("estimated_minutes") or item.get("minutes"), 30),
                "practice_suggestions": _as_list(item.get("practice_suggestions")),
            })
    return path[:6]


def _knowledge_candidates(value: Any, vision: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    source_points = _as_list(value) or _as_list(vision.get("possible_knowledge_points"))
    for item in source_points[:8]:
        item = item if isinstance(item, dict) else {"knowledge_point": item}
        point = _text(item.get("knowledge_point") or item.get("title") or item.get("name"))
        if not point:
            continue
        candidates.append({
            "course": _text(item.get("course") or vision.get("subject")),
            "knowledge_point": point,
            "parent": _text(item.get("parent")),
            "description": _text(item.get("description") or vision.get("summary")),
            "prerequisites": _as_list(item.get("prerequisites")),
            "common_mistakes": _as_list(item.get("common_mistakes")),
            "source_resource_id": _text(item.get("source_resource_id")),
            "confidence": _confidence(item.get("confidence"), _confidence(vision.get("confidence"), 0.5)),
            "review_status": "pending",
        })
    return candidates


def _mindmap_from_markdown(markdown: str, title: str) -> dict[str, Any]:
    children = []
    for line in markdown.splitlines():
        text = line.lstrip("#- ").strip()
        if text and text != title:
            children.append({"title": text, "children": []})
    return {"title": title or "图片知识结构", "children": children[:12]}


def _normalize_task_result(task_type: str, parsed: dict[str, Any], raw_text: str) -> dict[str, Any]:
    vision = _normalize_vision_result(parsed, raw_text)
    confidence = _confidence(parsed.get("confidence"), vision["confidence"])
    points = _as_list(parsed.get("knowledge_points") or parsed.get("possible_knowledge_points")) or vision["possible_knowledge_points"]
    question = _text(parsed.get("question_text") or vision.get("question_text") or vision.get("detected_text"))

    if task_type in {"explain_image_question", "solve_image_question"}:
        return {
            "question_text": question,
            "question_type": _friendly_value(parsed.get("question_type")),
            "subject": _text(parsed.get("subject") or vision.get("subject")),
            "knowledge_points": points,
            "answer": _text(parsed.get("answer")),
            "explanation_steps": _as_list(parsed.get("explanation_steps") or parsed.get("solution_steps")),
            "key_method": _text(parsed.get("key_method")),
            "common_mistakes": _as_list(parsed.get("common_mistakes")),
            "extracted_questions": vision.get("extracted_questions", []),
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, question, parsed.get("answer")),
            "evidence_from_image": _text(parsed.get("evidence_from_image") or vision.get("detected_text")),
            "vision_result": vision,
        }

    if task_type == "image_wrong_question_analysis":
        return {
            "question_text": question,
            "correct_answer": _text(parsed.get("correct_answer")),
            "student_answer": _text(parsed.get("student_answer") or vision.get("student_answer")),
            "mistake_type": _text(parsed.get("mistake_type")) or "待确认",
            "mistake_reason": _text(parsed.get("mistake_reason")),
            "weak_knowledge_points": _as_list(parsed.get("weak_knowledge_points") or points),
            "remediation_plan": _as_list(parsed.get("remediation_plan")),
            "similar_practice_suggestions": _as_list(parsed.get("similar_practice_suggestions")),
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, question, parsed.get("mistake_reason")),
            "vision_result": vision,
        }

    if task_type == "image_note_summary":
        return {
            "title": _text(parsed.get("title")) or _text(vision.get("summary"))[:40] or "图片笔记总结",
            "summary": _text(parsed.get("summary") or vision.get("summary")),
            "key_points": _as_list(parsed.get("key_points") or points),
            "structure": _as_list(parsed.get("structure")),
            "formulas": _as_list(parsed.get("formulas")),
            "definitions": _as_list(parsed.get("definitions")),
            "pitfalls": _as_list(parsed.get("pitfalls")),
            "next_actions": _as_list(parsed.get("next_actions")),
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, parsed.get("summary"), vision.get("detected_text")),
            "vision_result": vision,
        }

    if task_type == "image_to_mindmap":
        markdown = _text(parsed.get("markdown"))
        title = _text(parsed.get("title") or parsed.get("root_topic") or vision.get("summary"))[:80] or "图片知识结构"
        if not markdown and points:
            markdown = "# " + title + "\n" + "\n".join(f"- {point}" for point in points)
        mindmap = _as_dict(parsed.get("mindmap_json")) or _mindmap_from_markdown(markdown, title)
        return {
            "title": title,
            "root_topic": _text(parsed.get("root_topic")) or title,
            "markdown": markdown,
            "mindmap_json": mindmap,
            "mermaid": _text(parsed.get("mermaid")),
            "nodes_count": int(parsed.get("nodes_count") or len(points) or len(mindmap.get("children") or [])),
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, markdown, vision.get("detected_text")),
            "vision_result": vision,
        }

    if task_type == "image_to_flashcards":
        cards = _cards(parsed.get("cards"), vision)
        return {
            "title": _text(parsed.get("title")) or "图片复习卡片",
            "cards": cards,
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, cards, vision.get("detected_text")) or len(cards) < 3,
            "vision_result": vision,
        }

    if task_type == "image_to_learning_plan":
        return {
            "diagnosed_level": _text(parsed.get("diagnosed_level")) or "待评估",
            "weak_points": _as_list(parsed.get("weak_points") or points),
            "recommended_path": _recommended_path(parsed.get("recommended_path")),
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, parsed.get("recommended_path"), vision.get("detected_text")),
            "vision_result": vision,
        }

    if task_type == "image_to_variant_questions":
        variants = _variants(parsed.get("variants"))
        return {
            "source_question_summary": _text(parsed.get("source_question_summary") or question),
            "target_knowledge_points": points,
            "variants": variants,
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, question, variants) or len(variants) < 3,
            "vision_result": vision,
        }

    if task_type == "image_to_resource_bundle":
        result = {
            "understanding": _as_dict(parsed.get("understanding")) or vision,
            "explanation": _as_dict(parsed.get("explanation")),
            "note_summary": _as_dict(parsed.get("note_summary")),
            "mindmap": _as_dict(parsed.get("mindmap")),
            "flashcards": _as_list(parsed.get("flashcards") or parsed.get("cards")),
            "wrong_question_analysis": _as_dict(parsed.get("wrong_question_analysis")),
            "weak_points": _as_list(parsed.get("weak_points") or points),
            "next_actions": _as_list(parsed.get("next_actions")),
            "optional_variants": _variants(parsed.get("optional_variants") or parsed.get("variants")),
            "resource_save_candidate": _as_dict(parsed.get("resource_save_candidate")),
            "knowledge_candidates": _knowledge_candidates(parsed.get("knowledge_candidates"), vision),
            "confidence": confidence,
            "needs_manual_review": _needs_review(parsed, confidence, vision.get("detected_text"), parsed.get("understanding")),
        }
        if not result["resource_save_candidate"]:
            result["resource_save_candidate"] = {
                "title": _text(vision.get("summary"))[:60] or "图片学习资源包",
                "resource_type": "resource_bundle",
                "review_status": "pending",
                "saved": False,
            }
        result["resource_save_candidate"]["review_status"] = "pending"
        result["resource_save_candidate"]["saved"] = False
        return result

    return vision


def _vision_prompt(task_type: str) -> str:
    common = (
        "你是图片学习助手。只根据图片中可见内容回答，不要编造。"
        "必须只返回 JSON，不要 markdown。confidence 是 0 到 1。"
        "看不清、证据不足或题干不完整时 needs_manual_review=true，并给出 review_reasons、uncertain_question_indices、uncertain_fields。"
    )
    fields = {
        "image_understanding": "image_type, subject, detected_text, summary, possible_knowledge_points, extracted_questions, confidence, needs_manual_review, review_reasons, uncertain_question_indices, uncertain_fields",
        "explain_image_question": "extracted_questions, question_text, question_type, subject, knowledge_points, answer, explanation_steps, key_method, common_mistakes, confidence, needs_manual_review, review_reasons, uncertain_question_indices, uncertain_fields, evidence_from_image",
        "solve_image_question": "extracted_questions, question_text, question_type, subject, knowledge_points, answer, explanation_steps, key_method, common_mistakes, confidence, needs_manual_review, review_reasons, uncertain_question_indices, uncertain_fields, evidence_from_image",
        "image_wrong_question_analysis": "question_text, correct_answer, student_answer, mistake_type, mistake_reason, weak_knowledge_points, remediation_plan, similar_practice_suggestions, confidence, needs_manual_review, review_reasons, uncertain_question_indices, uncertain_fields",
        "image_note_summary": "title, summary, key_points, structure, formulas, definitions, pitfalls, next_actions, extracted_questions, confidence, needs_manual_review, review_reasons, uncertain_question_indices, uncertain_fields",
        "image_to_mindmap": "image_type, subject, detected_text, summary, possible_knowledge_points, extracted_questions, confidence, needs_manual_review, review_reasons, uncertain_question_indices, uncertain_fields",
        "image_to_flashcards": "title, cards, confidence, needs_manual_review; each card: front, back, knowledge_point, difficulty, card_type, source_evidence",
        "image_to_learning_plan": "diagnosed_level, weak_points, recommended_path, confidence, needs_manual_review; each recommended_path item: stage_title, objective, knowledge_points, estimated_minutes, practice_suggestions",
        "image_to_variant_questions": "source_question_summary, target_knowledge_points, variants, confidence, needs_manual_review; at least 3 variants if the source question is clear",
        "image_to_resource_bundle": "understanding, explanation, note_summary, mindmap, flashcards, wrong_question_analysis, weak_points, next_actions, optional_variants, resource_save_candidate, knowledge_candidates, confidence, needs_manual_review",
    }
    return f"{common} 当前任务 task_type={task_type}。返回字段：{fields.get(task_type, fields['image_understanding'])}。"


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
                points = knowledge_context.get("retrieved_points") or knowledge_context.get("knowledge_points") or knowledge_context.get("topics") or []
            if isinstance(points, list) and points:
                stages = [{"title": _text(point.get("title") if isinstance(point, dict) else point), "goal": "", "children": []} for point in points[:12]]
                topic = topic or _text(knowledge_context.get("course_name") if isinstance(knowledge_context, dict) else "")

        if not stages:
            return _response(
                status="needs_input",
                provider=self.provider,
                warnings=["missing learning_path or knowledge_context for mind map"],
                trace={"input_keys": sorted(context.keys())},
            )

        root = topic or _text(context.get("user_message")) or "Learning path"
        children = [{"title": stage["title"], "children": [{"title": child} for child in stage.get("children", [])]} for stage in stages if stage.get("title")]
        lines = ["mindmap", f"  root(({_safe_mermaid_label(root)}))"]
        markdown = [f"# {root}"]
        for stage in stages:
            lines.append(f"    {_safe_mermaid_label(stage['title'])}")
            markdown.append(f"- {stage['title']}")
            for child in stage.get("children", [])[:6]:
                lines.append(f"      {_safe_mermaid_label(child)}")
                markdown.append(f"  - {child}")

        return _response(
            status="success",
            provider=self.provider,
            result={
                "mindmap_json": {"title": root, "children": children},
                "markdown": "\n".join(markdown),
                "mermaid": "\n".join(lines),
                "stage_count": len(stages),
            },
            trace={"source": "learning_path" if learning_path else "knowledge_context"},
        )


class QwenVisionProvider:
    name = "QwenVisionProvider"
    provider = "qwen_vl"

    def __init__(self, post_json: Any | None = None) -> None:
        self.post_json = post_json or _json_post

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = _env("DASHSCOPE_API_KEY", "QWEN_API_KEY")
        model = _env("QWEN_VL_MODEL", default="qwen-vl-plus")
        base_url = _env("QWEN_BASE_URL", default="https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
        task_type = _text(context.get("task_type")) or "image_understanding"
        image, image_warning, image_kind = image_input_from_context(context)
        endpoint = ""
        try:
            endpoint = _qwen_chat_endpoint(base_url)
        except ValueError as exc:
            return _response(status="failed", provider=self.provider, warnings=[str(exc)], trace={"model": model, "base_url": base_url, "endpoint": endpoint, "task_type": task_type, "image_input_kind": image_kind, "payload_image_url_preview": image[:80], "exception_type": type(exc).__name__, "exception_message": str(exc)})
        if not api_key:
            return _response(status="provider_not_configured", provider=self.provider, warnings=["Qwen vision provider is not configured."], trace={"required_env": ["DASHSCOPE_API_KEY or QWEN_API_KEY"]})
        if not image:
            return _response(status="needs_input", provider=self.provider, warnings=[image_warning or "missing image input"], trace={"input_keys": sorted(context.keys()), "model": model, "base_url": base_url, "endpoint": endpoint, "task_type": task_type, "image_input_kind": image_kind})

        prompt = _vision_prompt(task_type)
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image}},
                ],
            }],
            "temperature": 0.1,
        }
        trace = {"model": model, "base_url": base_url, "endpoint": endpoint, "task_type": task_type, "image_input_kind": image_kind, "payload_image_url_preview": image[:80]}
        try:
            body = self.post_json(endpoint, payload, api_key, int(os.getenv("QWEN_TIMEOUT", "60")))
            raw_text = _text(body.get("choices", [{}])[0].get("message", {}).get("content"))
            try:
                parsed = parse_safe(raw_text)
                status = "success"
            except Exception:
                parsed = {}
                status = "partial_success"
            result = _ensure_review_fields(
                _normalize_task_result(task_type, parsed, raw_text),
                parsed,
                raw_text,
                parsed.get("detected_text"),
                parsed.get("question_text"),
                parsed.get("answer"),
            )
            if result.get("needs_manual_review") and status == "success":
                status = "needs_manual_review"
            return _response(
                status=status,
                provider=self.provider,
                result=result,
                trace=trace,
            ) | {"model": model, "raw_text": raw_text}
        except (HttpClientError, httpx.HTTPError, TimeoutError, OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            failed_trace = {**trace, "exception_type": type(exc).__name__, "exception_message": str(exc)}
            if isinstance(exc, HttpClientError):
                failed_trace["http_status"] = exc.http_status
                failed_trace["response_body_preview"] = exc.response_body_preview
            return _response(status="failed", provider=self.provider, warnings=[str(exc)], trace=failed_trace)


class QwenImageProvider:
    name = "QwenImageProvider"
    provider = "qwen_image"

    def __init__(self, post_json: Any | None = None) -> None:
        self.post_json = post_json or _json_post

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = _env("DASHSCOPE_API_KEY", "QWEN_API_KEY")
        model = _env("QWEN_IMAGE_MODEL", default="qwen-image")
        endpoint = _env("QWEN_IMAGE_ENDPOINT") or f"{_env('QWEN_IMAGE_BASE_URL', 'QWEN_BASE_URL', default='https://dashscope.aliyuncs.com/compatible-mode/v1').rstrip('/')}/images/generations"
        if not api_key or not model or not endpoint:
            return _response(status="provider_not_configured", provider=self.provider, warnings=["Qwen image provider is not configured."], trace={"required_env": ["DASHSCOPE_API_KEY or QWEN_API_KEY", "QWEN_IMAGE_MODEL", "QWEN_IMAGE_ENDPOINT or QWEN_IMAGE_BASE_URL"]})
        prompt = _text(context.get("prompt") or context.get("user_message") or context.get("topic"))
        if not prompt:
            return _response(status="needs_input", provider=self.provider, warnings=["missing image prompt"])
        try:
            body = self.post_json(endpoint, {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}, api_key, int(os.getenv("QWEN_TIMEOUT", "60")))
            urls = []
            for item in body.get("data") or body.get("output", {}).get("results") or []:
                if isinstance(item, dict) and _text(item.get("url")):
                    urls.append(_text(item.get("url")))
            result = {"image_urls": urls, "task_id": _text(body.get("task_id") or body.get("output", {}).get("task_id")), "remote_result": body}
            return _response(status="success" if urls or result["task_id"] else "partial_success", provider=self.provider, result=result, trace={"model": model, "endpoint": endpoint})
        except Exception as exc:
            return _response(status="failed", provider=self.provider, warnings=[str(exc)], trace={"model": model, "endpoint": endpoint})


def _micro_lesson_script(context: dict[str, Any]) -> dict[str, Any]:
    topic = _text(context.get("topic") or context.get("user_message")) or "learning topic"
    script = f"Opening: introduce {topic}.\nExplain the core idea with one simple example.\nClose with a quick recap and one practice question."
    return {
        "script": script,
        "storyboard": [
            {"scene": 1, "title": "Hook", "description": f"Introduce why {topic} matters."},
            {"scene": 2, "title": "Concept", "description": f"Explain the key idea of {topic}."},
            {"scene": 3, "title": "Practice", "description": "Show one short practice prompt."},
        ],
    }


class WanVideoProvider:
    name = "WanVideoProvider"
    provider = "wan_video"

    def __init__(self, post_json: Any | None = None) -> None:
        self.post_json = post_json or _json_post

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        script = _micro_lesson_script(context)
        api_key = _env("DASHSCOPE_API_KEY", "WAN_API_KEY")
        model = _env("WAN_VIDEO_MODEL", default="wanx2.1-t2v-turbo")
        endpoint = _env("WAN_VIDEO_ENDPOINT")
        if not api_key or not model or not endpoint:
            return _response(status="script_ready_provider_not_configured", provider=self.provider, result=script, warnings=["Wan video provider is not configured."], trace={"required_env": ["DASHSCOPE_API_KEY or WAN_API_KEY", "WAN_VIDEO_MODEL", "WAN_VIDEO_ENDPOINT"]})
        try:
            body = self.post_json(endpoint, {"model": model, "prompt": script["script"]}, api_key, int(os.getenv("WAN_TIMEOUT", "60")))
            result = {**script, "task_id": _text(body.get("task_id") or body.get("output", {}).get("task_id")), "task_status": _text(body.get("status") or body.get("output", {}).get("task_status") or "submitted"), "video_url": _text(body.get("video_url") or body.get("output", {}).get("video_url")), "remote_result": body}
            return _response(status="success", provider=self.provider, result=result, trace={"model": model, "endpoint": endpoint})
        except Exception as exc:
            return _response(status="failed", provider=self.provider, result=script, warnings=[str(exc)], trace={"model": model, "endpoint": endpoint})
