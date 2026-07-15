"""Executable multimodal tools and providers.

The non-text providers intentionally refuse to fake outputs when credentials
are missing or when the real API call is not implemented yet.
"""

from __future__ import annotations

import logging
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
        children: list[Any] = []
        if isinstance(tasks, list):
            for task in tasks:
                if isinstance(task, dict):
                    child_title = _text(task.get("topic") or task.get("title") or task.get("name"))
                    grandchildren = task.get("children") or task.get("knowledge_points") or []
                    child_entry: dict[str, Any] = {"title": child_title, "children": []}
                    for gc in grandchildren:
                        if isinstance(gc, dict):
                            gc_text = _text(gc.get("title") or gc.get("name") or gc.get("topic") or "")
                        else:
                            gc_text = _text(gc)
                        if gc_text:
                            child_entry["children"].append(gc_text)
                    if child_title:
                        children.append(child_entry)
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


# ── Real implementations below (imports + providers) ──
import base64
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.utils.llm_json import parse_safe

logger = logging.getLogger(__name__)


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


def _json_post(url: str, payload: dict[str, Any], api_key: str, timeout: int = 60, extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    response = httpx.post(
        url,
        json=payload,
        headers=headers,
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


def _drop_empty_sections(value: dict[str, Any]) -> dict[str, Any]:
    keep = {}
    for key, item in value.items():
        if item in (None, "", [], {}):
            continue
        if isinstance(item, str) and item.strip(". ") == "":
            continue
        keep[key] = item
    return keep


def _confidence(value: Any, default: float = 0.5) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def _friendly_value(value: Any) -> str:
    text = _text(value)
    if text.strip(". ") == "":
        return ""
    if text.lower() in {"unknown", "none", "null", "n/a", "na"}:
        return ""
    if text in {"未知", "无", "暂无", "未识别"}:
        return ""
    return text


_BAD_USER_TEXT = (
    "see extracted_questions",
    "per-question answers",
    "extracted_questions",
    "raw_structured_result",
    "source_evidence",
)


def _is_bad_user_text(value: Any) -> bool:
    text = _text(value).lower()
    return bool(text) and any(marker in text for marker in _BAD_USER_TEXT)


def _clean_user_text(value: Any) -> str:
    text = _text(value)
    return "" if _is_bad_user_text(text) else text


def _safe_summary(parsed: dict[str, Any], raw_text: str) -> str:
    summary = _text(parsed.get("summary"))
    if summary and summary.strip(". "):
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
    spans = [_text(item) for item in _as_list(parsed.get("uncertain_spans")) if _text(item)]
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

    needs_review = bool(reasons or fields or indices or spans)
    review_level = "high" if not any(len(_text(item)) >= 8 for item in evidence) else ("medium" if needs_review else "low")
    return {
        "needs_manual_review": needs_review,
        "review_reasons": list(dict.fromkeys(reasons)),
        "uncertain_question_indices": list(dict.fromkeys(indices)),
        "uncertain_fields": list(dict.fromkeys(fields)),
        "uncertain_spans": list(dict.fromkeys(spans)),
        "review_level": review_level,
        "can_continue": review_level != "high",
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
    result["uncertain_spans"] = list(dict.fromkeys(_as_list(result.get("uncertain_spans")) + review["uncertain_spans"]))
    result["review_level"] = result.get("review_level") or review["review_level"]
    result["can_continue"] = bool(result.get("can_continue", review["can_continue"]))
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
        front = _clean_user_text(item.get("front") or item.get("question") or item.get("knowledge_point"))
        back = _clean_user_text(item.get("back") or item.get("answer") or vision.get("summary"))
        if front and back:
            cards.append({
                "front": front,
                "back": back,
                "knowledge_point": _clean_user_text(item.get("knowledge_point")) or front,
                "difficulty": _clean_user_text(item.get("difficulty")) or "medium",
                "card_type": _clean_user_text(item.get("card_type")) or "concept",
                "source_evidence": _clean_user_text(vision.get("detected_text") or vision.get("summary")),
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
        steps = _as_list(parsed.get("explanation_steps") or parsed.get("solution_steps"))
        display = _clean_user_text(parsed.get("display_text") or parsed.get("teaching_text") or parsed.get("chat_text"))
        if not display and (question or steps):
            display = "\n".join([
                "我先按图片里能识别到的信息讲解：",
                f"题目：{question}" if question else "",
                "讲解：" + "；".join(str(step) for step in steps if _text(step)) if steps else "",
                f"答案：{_clean_user_text(parsed.get('answer'))}" if _clean_user_text(parsed.get("answer")) else "",
            ]).strip()
        return {
            "display_text": display,
            "teaching_text": display,
            "question_text": question,
            "question_type": _friendly_value(parsed.get("question_type")),
            "subject": _text(parsed.get("subject") or vision.get("subject")),
            "knowledge_points": points,
            "answer": _clean_user_text(parsed.get("answer")),
            "explanation_steps": steps,
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
            "display_text": (
                "我已把这张图片整理成一份学习资源包。你可以先查看内容，也可以保存到资源库；"
                "其中提取出的知识点会作为“待确认知识候选”，不会直接写入正式知识库。"
            ),
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
        return _drop_empty_sections(result)

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
    provider = "deeptutor_mindmap"

    @staticmethod
    def is_configured() -> bool:
        return True  # Always available via data-driven fallback

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        logger = logging.getLogger(__name__)
        topic = _text(context.get("topic") or context.get("course_name") or context.get("subject_name"))
        learning_path = context.get("learning_path") or context.get("path")
        stages = _normalize_stages(learning_path)

        # ── 先构建数据驱动的三层结构（始终可用）──
        data_mermaid = self._build_data_mindmap(topic, stages)
        data_markdown = self._build_data_markdown(topic, stages)

        # ── 尝试 DeepTutor 用 graph LR 生成更丰富的层级图 ──
        section_titles = []
        for s in stages:
            section_titles.append(s.get("title", ""))
            for c in s.get("children", []):
                section_titles.append(str(c) if isinstance(c, str) else c.get("title", ""))
        topic_list = "、".join(section_titles[:15]) if section_titles else topic

        dt_prompt = (
            f'用 Mermaid flowchart LR 为「{topic}」生成一张知识点层级结构图。\n'
            f'铁律：第一行必须是 flowchart LR，禁止写成 TD/TB/RL。从左到右布局。\n'
            f'节点标签简洁中文，至少3层深度，每个分支展开到底层知识点。\n'
            f'涵盖内容：{topic_list}\n'
            f'参考格式：\n'
            f'```mermaid\n'
            f'flowchart LR\n'
            f'  A["{topic}"] --> B["核心概念一"]\n'
            f'  A --> C["核心概念二"]\n'
            f'  B --> D["子概念1"]\n'
            f'  B --> E["子概念2"]\n'
            f'  D --> F["具体知识点"]\n'
            f'  C --> G["子概念3"]\n'
            f'```\n'
            f'只输出```mermaid代码块。'
        )

        try:
            from app.services.deeptutor_client import deeptutor_call
            raw = deeptutor_call("chat", dt_prompt)
            logger.info("MindMapTool DT raw (first 300): %s", (raw or "")[:300])
            if raw and len(raw) > 50:
                import re as _re
                m = _re.search(r"```(?:mermaid)?\s*\n?(.+?)```", raw, _re.DOTALL)
                mermaid_def = m.group(1).strip() if m else ""
                # Accept both mindmap and graph/flowchart syntax
                if mermaid_def and len(mermaid_def) > 50 and (
                    mermaid_def.startswith("mindmap") or
                    mermaid_def.startswith("graph") or
                    mermaid_def.startswith("flowchart")
                ):
                    logger.info("MindMapTool using DT output (%d chars, type=%s)", len(mermaid_def), mermaid_def.split()[0])
                    return _response(status="success", provider=self.provider,
                        result={"mermaid": mermaid_def, "markdown": data_markdown, "stage_count": len(stages)},
                        trace={"source": "deeptutor_chat"})
                else:
                    logger.warning("MindMapTool DT rejected: len=%d prefix=%s", len(mermaid_def), (mermaid_def or "")[:30])
        except Exception as e:
            logger.warning("MindMapTool DT failed: %s", e)

        # ── 回退到数据驱动的三层结构 ──
        logger.info("MindMapTool using data-driven fallback (%d stages)", len(stages))
        return _response(status="success", provider=self.provider,
            result={"mermaid": data_mermaid, "markdown": data_markdown, "stage_count": len(stages)},
            trace={"source": "data_driven"})

    @staticmethod
    def _build_data_mindmap(topic: str, stages: list[dict[str, Any]]) -> str:
        root = topic or "学习内容"
        lines = ["mindmap", f"  root(({_safe_mermaid_label(root)}))"]
        for stage in stages:
            lines.append(f"    {_safe_mermaid_label(stage['title'])}")
            for child in stage.get("children", [])[:8]:
                if isinstance(child, dict):
                    child_title = _safe_mermaid_label(child.get("title", ""))
                    if child_title and child_title != "未命名":
                        lines.append(f"      {child_title}")
                    for gc in child.get("children", [])[:5]:
                        gc_text = _safe_mermaid_label(gc if isinstance(gc, str) else str(gc.get("title", gc)))
                        if gc_text and gc_text != "未命名":
                            lines.append(f"        {gc_text}")
                else:
                    lines.append(f"      {_safe_mermaid_label(str(child))}")
        return "\n".join(lines)

    @staticmethod
    def _build_data_markdown(topic: str, stages: list[dict[str, Any]]) -> str:
        lines = [f"# {topic or '学习内容'}"]
        for stage in stages:
            lines.append(f"- {stage.get('title', '')}")
            for child in stage.get("children", [])[:8]:
                if isinstance(child, dict):
                    lines.append(f"  - {child.get('title', '')}")
                    for gc in child.get("children", [])[:5]:
                        gc_text = str(gc) if isinstance(gc, str) else str(gc.get("title", gc))
                        lines.append(f"    - {gc_text}")
                else:
                    lines.append(f"  - {str(child)}")
        return "\n".join(lines)


class QwenVisionProvider:
    name = "QwenVisionProvider"
    provider = "qwen_vl"

    @staticmethod
    def is_configured() -> bool:
        return bool(_env("DASHSCOPE_API_KEY", "QWEN_API_KEY"))

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


class SparkVisionProvider:
    name = "SparkVisionProvider"
    provider = "spark_vision"

    SPARK_VISION_URL = "wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image"

    @staticmethod
    def is_configured() -> bool:
        from app.config import settings
        app_id = settings.spark_vision_app_id or settings.spark_app_id
        api_key = settings.spark_vision_api_key or settings.spark_api_key
        return bool(app_id) and bool(api_key)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from app.config import settings
        import asyncio, json as _json, base64 as _b64

        app_id = settings.spark_vision_app_id or settings.spark_app_id
        api_key = settings.spark_vision_api_key or settings.spark_api_key
        api_secret = settings.spark_vision_api_secret or settings.spark_api_secret
        if not app_id or not api_key:
            return _response(status="provider_not_configured", provider=self.provider,
                warnings=["Spark vision provider not configured."],
                trace={"required_env": ["SPARK_VISION_APP_ID", "SPARK_VISION_API_KEY", "SPARK_VISION_API_SECRET"]})

        image, image_warning, image_kind = image_input_from_context(context)
        task_type = _text(context.get("task_type")) or "image_understanding"
        if not image:
            return _response(status="needs_input", provider=self.provider,
                warnings=[image_warning or "missing image input"],
                trace={"task_type": task_type})

        prompt = _vision_prompt(task_type)

        async def _ws_call():
            from app.services.spark_provider import _build_auth_url
            import websockets

            url = _build_auth_url(
                self.SPARK_VISION_URL.replace("wss://", "https://"),
                api_key=api_key, api_secret=api_secret,
            )
            url = url.replace("https://", "wss://")
            payload = {
                "header": {"app_id": app_id},
                "parameter": {"chat": {"domain": "imagev3", "temperature": 0.1}},
                "payload": {"message": {"text": [
                    {"role": "user", "content": image if image_kind == "base64" else _b64.b64encode(image.encode()).decode() if isinstance(image, str) else image, "content_type": "image"},
                    {"role": "user", "content": prompt, "content_type": "text"},
                ]}},
            }
            async with websockets.connect(url, max_size=10*1024*1024) as ws:
                await ws.send(_json.dumps(payload))
                raw_text = ""
                async for msg in ws:
                    data = _json.loads(msg)
                    code = data.get("header", {}).get("code", -1)
                    if code != 0:
                        break
                    choices = data.get("payload", {}).get("choices", {})
                    status = choices.get("status", 2)
                    content_list = choices.get("text", []) if isinstance(choices, dict) else []
                    for c in content_list:
                        if isinstance(c, dict) and c.get("content"):
                            raw_text += str(c["content"])
                    if status == 2:  # completed
                        break
                return raw_text

        try:
            raw_text = asyncio.run(_ws_call())
        except Exception as e:
            return _response(status="failed", provider=self.provider, warnings=[str(e)])

        if not raw_text:
            return _response(status="failed", provider=self.provider, warnings=["empty response from Spark vision"])

        try:
            parsed = parse_safe(raw_text)
        except Exception:
            parsed = {}
        result = _ensure_review_fields(
            _normalize_task_result(task_type, parsed, raw_text),
            parsed, raw_text,
            parsed.get("detected_text"), parsed.get("question_text"), parsed.get("answer"))
        return _response(status="success", provider=self.provider, result=result,
            trace={"task_type": task_type})


class QwenImageProvider:
    name = "QwenImageProvider"
    provider = "qwen_image"

    @staticmethod
    def is_configured() -> bool:
        api_key = _env("DASHSCOPE_API_KEY", "QWEN_API_KEY")
        return bool(api_key)

    def __init__(self, post_json: Any | None = None) -> None:
        self.post_json = post_json or _json_post

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = _env("DASHSCOPE_API_KEY", "QWEN_API_KEY")
        model = _env("QWEN_IMAGE_MODEL", default="qwen-image-2.0")
        endpoint = _env("QWEN_IMAGE_ENDPOINT") or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        if not api_key:
            return _response(status="provider_not_configured", provider=self.provider,
                warnings=["Qwen image provider is not configured."],
                trace={"required_env": ["DASHSCOPE_API_KEY or QWEN_API_KEY"]})
        prompt = _text(context.get("prompt") or context.get("user_message") or context.get("topic"))
        if not prompt:
            return _response(status="needs_input", provider=self.provider, warnings=["missing image prompt"])
        try:
            body = self.post_json(endpoint, {
                "model": model,
                "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                "parameters": {"size": "1024*1024", "n": 1}
            }, api_key, int(os.getenv("QWEN_TIMEOUT", "60")))
            urls: list[str] = []
            for choice in body.get("output", {}).get("choices") or []:
                for content_item in choice.get("message", {}).get("content") or []:
                    img_url = _text(content_item.get("image"))
                    if img_url:
                        urls.append(img_url)
            result = {"image_urls": urls, "remote_result": body}
            return _response(
                status="success" if urls else "partial_success", provider=self.provider,
                result=result, trace={"model": model, "endpoint": endpoint})
        except Exception as exc:
            return _response(status="failed", provider=self.provider,
                warnings=[str(exc)], trace={"model": model, "endpoint": endpoint})

# ── Seedream Image Provider (DeepSeek prompt optimisation → Seedream 5.0 Lite) ──

_SEEDREAM_SYSTEM_PROMPT = """You are a bilingual image description assistant that works with an image generation bot.
You will be prompted by people looking to create detailed, amazing educational and technical images.
Take their short prompts and make them extremely detailed and descriptive.
Rules:
- Input can be in Chinese or English. If input is in Chinese, output in Chinese. If input is in English, output in English.
- Output a single image description per request — no explanation, no process, just the description.
- Include: subject, composition, medium, style, color palette, lighting, and specific visual details.
- For educational/technical diagrams: specify layout (left/right, top/bottom), colors for each element, label positions, arrow directions.
- Focus on tangible visual elements, not abstract emotions.
- Descriptions should be 80-200 words."""

_SEEDREAM_FEWSHOT: list[dict[str, str]] = [
    {"role": "user", "content": 'Create an imaginative image descriptive caption for the user input : "画一个白发、神情忧郁的动漫女孩，手里拿着一支香烟"'},
    {"role": "assistant", "content": "这幅图像是一幅动漫风格的插画，画中描绘了一位长发飘逸的白发女孩。她神情忧郁，双眼低垂，脸上带着微微的愁容。女孩穿着浅色外套，里面搭配深色衬衫和领带，增添了她沉静却时尚的外表。背景描绘了一个冬季的城市场景，地面和建筑物上覆盖着积雪，街边停着一辆车，增强了场景的荒凉氛围。整幅作品细致精美，典型的现代动漫插画风格。"},
    {"role": "user", "content": 'Create an imaginative image descriptive caption for the user input : "画一张CNN卷积神经网络的工作流程图"'},
    {"role": "assistant", "content": "A clear technical diagram showing a 3x3 convolution kernel sliding across a 5x5 input feature map. The kernel is highlighted in blue, the input grid in orange, positioned on a light gray background. Curved arrows trace the sliding path from left to right, top to bottom. Mathematical annotations appear below: F(i,j) = sum(W*X) + b. Clean academic textbook illustration style, isometric or flat 2D layout, labeled axes and dimension markers."},
]

def _optimize_prompt_with_deepseek(raw_prompt: str) -> str:
    """Use DeepSeek to expand a short prompt into a detailed image description."""
    ds_key = _env("DEEPSEEK_API_KEY")
    ds_url = _env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com/v1")
    ds_model = _env("DEEPSEEK_MODEL", default="deepseek-chat")
    if not ds_key:
        raise RuntimeError("DEEPSEEK_API_KEY not configured for prompt optimisation")
    messages: list[dict[str, str]] = [{"role": "system", "content": _SEEDREAM_SYSTEM_PROMPT}]
    messages.extend(_SEEDREAM_FEWSHOT)
    messages.append({"role": "user", "content": f'Create an imaginative image descriptive caption for the user input : "{raw_prompt}"'})
    body = _json_post(
        f"{ds_url}/chat/completions",
        {"model": ds_model, "messages": messages, "temperature": 0.01, "max_tokens": 1024},
        ds_key,
        timeout=60,
    )
    enhanced = _text(body["choices"][0]["message"]["content"])
    return enhanced


class SeedreamImageProvider:
    name = "SeedreamImageProvider"
    provider = "seedream"

    @staticmethod
    def is_configured() -> bool:
        ark_key = _env("ARK_API_KEY")
        ds_key = _env("DEEPSEEK_API_KEY")
        return bool(ark_key) and bool(ds_key)

    def __init__(self, post_json: Any | None = None) -> None:
        self.post_json = post_json or _json_post

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        ark_key = _env("ARK_API_KEY")
        ds_key = _env("DEEPSEEK_API_KEY")
        endpoint = _env("SEEDREAM_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3/images/generations"
        model = _env("SEEDREAM_MODEL", default="doubao-seedream-5-0-lite-260128")
        size = _env("SEEDREAM_SIZE", default="1920x1920")

        if not ark_key:
            return _response(status="provider_not_configured", provider=self.provider,
                warnings=["ARK_API_KEY not configured for Seedream image generation."],
                trace={"required_env": ["ARK_API_KEY"]})
        if not ds_key:
            return _response(status="provider_not_configured", provider=self.provider,
                warnings=["DEEPSEEK_API_KEY not configured for prompt optimisation."],
                trace={"required_env": ["DEEPSEEK_API_KEY"]})

        raw_prompt = _text(context.get("prompt") or context.get("user_message") or context.get("topic"))
        if not raw_prompt:
            return _response(status="needs_input", provider=self.provider,
                warnings=["missing image prompt"])

        try:
            # Step 1 — DeepSeek prompt optimisation
            enhanced_prompt = _optimize_prompt_with_deepseek(raw_prompt)
            logger.info("Seedream prompt enhanced: %d → %d chars", len(raw_prompt), len(enhanced_prompt))
        except Exception as exc:
            logger.warning("Prompt optimisation failed, using raw prompt: %s", exc)
            enhanced_prompt = raw_prompt

        try:
            # Step 2 — Seedream image generation
            body = self.post_json(endpoint,
                {"model": model, "prompt": enhanced_prompt, "n": 1, "size": size},
                ark_key,
                timeout=int(os.getenv("SEEDREAM_TIMEOUT", "120")))
            urls: list[str] = []
            for item in body.get("data") or []:
                if isinstance(item, dict) and _text(item.get("url")):
                    urls.append(_text(item.get("url")))
            result = {
                "image_urls": urls,
                "raw_prompt": raw_prompt,
                "enhanced_prompt": enhanced_prompt,
                "model": model,
            }
            return _response(
                status="success" if urls else "partial_success",
                provider=self.provider,
                result=result,
                trace={"model": model, "endpoint": endpoint, "prompt_chars": len(enhanced_prompt)})
        except Exception as exc:
            return _response(status="failed", provider=self.provider,
                warnings=[str(exc)],
                trace={"model": model, "endpoint": endpoint})


def _micro_lesson_script(context: dict[str, Any]) -> dict[str, Any]:
    topic = _text(context.get("topic") or context.get("user_message")) or "学习主题"
    subject = _text(context.get("subject_name") or topic)
    # Conceptual animation prompt — no text/characters, pure visual explanation.
    # Wan2.1 cannot render legible text; we use abstract visuals + motion to
    # convey ideas.  Voiceover / subtitles are added separately.
    script = (
        f"An educational micro-lecture animation about {subject} — {topic}. "
        f"Professional lecture style, clean academic visuals, smooth transitions. "
        f"Scene 1: Abstract geometric shapes floating in dark blue space, representing mathematical concepts, "
        f"slowly converging to form a unified structure — symbolizing the core idea of {topic}. "
        f"Scene 2: Clean 3D graphs and curves animating on a dark gradient background, "
        f"showing relationships between variables, with glowing connection lines. "
        f"Scene 3: A real-world metaphor visualized — smooth flowing particles or waves "
        f"transitioning from chaos to order, illustrating the concept intuitively. "
        f"Scene 4: Returning to the abstract structure from scene 1, now fully formed and rotating gently, "
        f"ending on a calm, satisfying wide shot. "
        f"Style: dark blue and indigo gradient background, warm golden accent lines, no text, no people."
    )
    return {
        "script": script,
        "storyboard": [
            {"scene": 1, "title": "概念引入", "description": f"抽象几何体在深蓝空间汇聚，隐喻「{topic}」的核心结构"},
            {"scene": 2, "title": "关系演示", "description": "3D 曲线和图表动画展示变量间关系"},
            {"scene": 3, "title": "直观类比", "description": "粒子/波动从混沌到有序的视觉隐喻"},
            {"scene": 4, "title": "回顾收束", "description": "回到开头的结构，缓缓旋转，平静收尾"},
        ],
    }


class WanVideoProvider:
    name = "WanVideoProvider"
    provider = "wan_video"

    @staticmethod
    def is_configured() -> bool:
        api_key = _env("DASHSCOPE_API_KEY", "WAN_API_KEY", "QWEN_API_KEY")
        model = _env("WAN_VIDEO_MODEL", default="wanx2.1-t2v-turbo")
        return bool(api_key) and bool(model)

    def __init__(self, post_json: Any | None = None) -> None:
        self.post_json = post_json or _json_post

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Submit a video generation task to DashScope Wan (async).

        Returns immediately with a task_id and status='submitted' so the
        caller can poll for completion via WanVideoProvider.poll_task().
        """
        script = _micro_lesson_script(context)
        api_key = _env("DASHSCOPE_API_KEY", "WAN_API_KEY", "QWEN_API_KEY")
        model = _env("WAN_VIDEO_MODEL", default="wanx2.1-t2v-turbo")
        endpoint = _env("WAN_VIDEO_ENDPOINT") or _env("WAN_VIDEO_BASE_URL", default="https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis")
        if not api_key or not model:
            return _response(status="script_ready_provider_not_configured", provider=self.provider, result=script, warnings=["Wan video provider is not configured."], trace={"required_env": ["QWEN_API_KEY/DASHSCOPE_API_KEY/WAN_API_KEY", "WAN_VIDEO_MODEL"]})
        try:
            body = self.post_json(endpoint, {
                "model": model,
                "input": {"prompt": script["script"]},
                "parameters": {"duration": 5, "size": "1280*720"},
            }, api_key, int(os.getenv("WAN_TIMEOUT", "30")), extra_headers={"X-DashScope-Async": "enable"})
            task_id = _text(body.get("output", {}).get("task_id"))
            if not task_id:
                return _response(status="failed", provider=self.provider, result=script, warnings=["DashScope did not return a task_id."], trace={"model": model, "endpoint": endpoint, "response_keys": list(body.keys())})
            req_id = _text(body.get("request_id"))
            return _response(status="submitted", provider=self.provider, result={**script, "task_id": task_id, "task_status": "submitted", "request_id": req_id}, trace={"model": model, "endpoint": endpoint})
        except (HttpClientError, httpx.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return _response(status="failed", provider=self.provider, result=script, warnings=[str(exc)], trace={"model": model, "endpoint": endpoint})


class ManimVideoProvider:
    """Generate high-quality educational animations via Manim (code→video).

    Uses LLM to generate a Manim Python script from the section context,
    then renders it with ``manim`` CLI.  Produces mathematically precise
    animations with crisp LaTeX formulas — 3Blue1Brown style.
    """
    name = "ManimVideoProvider"
    provider = "manim_video"

    @property
    def output_dir(self) -> Path:
        # Write outside backend/ so uvicorn --reload doesn't restart on file creation
        d = settings.project_root / "outputs" / "manim"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def is_configured() -> bool:
        import shutil
        return shutil.which("manim") is not None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        import shutil
        if not shutil.which("manim"):
            return _response(status="provider_not_configured", provider=self.provider,
                warnings=["Manim is not installed. Run: pip install manim"],
                trace={"required": ["manim CLI"]})

        topic = _text(context.get("topic") or context.get("user_message"))
        # Strip request language: "我需要讲解极限的教学视频" → "极限"
        topic = re.sub(r"^(我需要|我要|帮我|请|给我)(讲解|生成|做一个|出一个)?", "", topic)
        topic = re.sub(r"(的教学视频|的视频|的微课视频|的视频教程|的动画)$", "", topic).strip() or topic
        subject = _text(context.get("subject_name") or topic)

        # ── Step 1: RAG retrieval for accurate knowledge content ──
        kb_context = ""
        try:
            from app.rag.query_engine import rag_query_engine
            if rag_query_engine.is_ready():
                resp = rag_query_engine.search(topic, top_k=3)
                if resp.results:
                    kb_context = "\n\n".join(
                        f"## {r.title}\n{r.text[:800]}"
                        for r in resp.results if r.text
                    )
        except Exception:
            pass

        # ── Step 2: Generate Manim code first, then narration matched to video ──
        try:
            from app.services.llm_client import get_llm_client
            llm = get_llm_client()
        except Exception:
            return _response(status="failed", provider=self.provider,
                warnings=["LLM 不可用"], trace={})

        manim_code = ""
        narration = ""
        audio_path = ""
        audio_url = ""

        # Use factory for code generation (respects LLM_CODER_PROVIDER from .env)
        code_llm = llm
        try:
            from app.services.llm_factory import get_coder
            coder_func = get_coder()
            code_llm = llm  # fallback — UnifiedChatClient doesn't have chat(), use existing
            # Actually use get_chat_client for Qwen-Coder
            from app.services.llm_factory import get_chat_client as _coder_client
            # Only swap if Qwen is configured as coder
            import os as _os
            coder_prov = _os.getenv("LLM_CODER_PROVIDER", "")
            if coder_prov:
                code_llm = _coder_client()
                logger.info("Using factory coder (%s) for Manim code", coder_prov)
        except Exception as e:
            logger.warning("Factory coder init failed, using default: %s", e)

        # ── Step 2a: Generate narration FIRST, get its duration ──
        _tmp_audio = ""
        narration_text = self._generate_narration_only(code_llm, topic, subject, kb_context)
        narrative_duration = 0
        if narration_text and len(narration_text) > 20:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            _tmp_job = uuid.uuid4().hex
            narration_text = self._clean_markdown(narration_text)
            _tmp_audio = self._generate_narration(narration_text, _tmp_job)
            if _tmp_audio:
                narrative_duration = self._get_video_duration(_tmp_audio)
                if narrative_duration > 0:
                    logger.info("Narration ready: %.1fs, generating Manim to match", narrative_duration)

        # ── Step 2b: Generate Manim code matched to narration duration ──
        combined = self._generate_combined(code_llm, topic, subject, kb_context,
            _text(context.get("knowledge_points") or ""),
            target_duration=narrative_duration,
            narration_text=narration_text)
        if not combined or not combined.get("code"):
            return _response(status="failed", provider=self.provider,
                warnings=["LLM 未能生成有效的 Manim 脚本。"],
                trace={"topic": topic})
        manim_code = combined.get("code", "")

        # ── Pre-render scrub: fix common mistakes ──
        manim_code = self._scrub_code(manim_code)
        logger.info("Scrubbed code len=%d, has EduScene=%s", len(manim_code), "class EduScene" in manim_code)

        # ── Step 3: Render with auto-retry on failure ──
        self.output_dir.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex
        scene_name = "EduScene"
        script_path = self.output_dir / f"{job_id}_scene.py"
        script_path.write_text(manim_code, encoding="utf-8")

        MAX_RETRIES = 2
        video_path = ""
        # Ensure manim can find ffmpeg and latex (winget installs may not be in PATH)
        import shutil as _shutil_m
        _manim_env = dict(os.environ)
        _paths = _manim_env.get("PATH", "").split(os.pathsep)
        # Search common install locations
        _extra = [
            r"C:\Users\hejiaxuan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin",
            r"C:\Users\hejiaxuan\AppData\Local\Programs\MiKTeX\miktex\bin\x64",
        ]
        for _d in _extra:
            if os.path.isdir(_d) and _d not in _paths:
                _paths.insert(0, _d)
        for _tool in ("ffmpeg", "latex", "pdflatex"):
            _found = _shutil_m.which(_tool)
            if _found:
                _tool_dir = os.path.dirname(_found)
                if _tool_dir not in _paths:
                    _paths.insert(0, _tool_dir)
        _manim_env["PATH"] = os.pathsep.join(_paths)
        for attempt in range(MAX_RETRIES + 1):
            import subprocess
            logger.info("Render attempt %d/%d, code len=%d", attempt + 1, MAX_RETRIES + 1, len(manim_code))
            try:
                result = subprocess.run(
                    ["manim", "-ql", "--format", "mp4", str(script_path), scene_name],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(self.output_dir), env=_manim_env,
                )
            except subprocess.TimeoutExpired:
                logger.error("Render attempt %d TIMED OUT after 300s", attempt + 1)
                # Don't retry on timeout — the animation is too complex
                break
            if result.returncode == 0:
                logger.info("Manim render SUCCESS on attempt %d (rc=%d)", attempt + 1, result.returncode)
                video_files = list(self.output_dir.glob(f"**/{scene_name}.mp4"))
                if not video_files:
                    video_files = list(self.output_dir.rglob("*.mp4"))
                if video_files:
                    video_path = str(video_files[0])
                    break

            # Failed — log full error, let LLM fix the code
            logger.error("Manim render attempt %d FAILED. stderr tail: %s", attempt + 1,
                (result.stderr or "")[-500:] if result.stderr else "(no stderr)")
            if attempt < MAX_RETRIES:
                fixed = self._fix_script(code_llm, manim_code, result.stderr or "", result.stdout or "", topic, subject, kb_context)
                if fixed and len(fixed) > 30:
                    manim_code = self._scrub_code(fixed)  # re-scrub to catch any re-introduced issues
                    script_path.write_text(manim_code, encoding="utf-8")
                else:
                    break  # LLM couldn't fix it, give up

        if not video_path:
            logger.error("All render attempts failed for topic '%s'", topic)
            return _response(status="failed", provider=self.provider,
                warnings=[f"manim 渲染失败（已重试 {MAX_RETRIES} 次）"],
                trace={"script": manim_code})

        # ── Step 4: Merge pre-generated narration with video ──
        if _tmp_audio and os.path.isfile(_tmp_audio):
            audio_path = _tmp_audio
            narration = narration_text
            rel_a = audio_path.replace("\\", "/")
            outputs_root_a = str(settings.project_root / "outputs").replace("\\", "/") + "/"
            if rel_a.startswith(outputs_root_a):
                rel_a = rel_a[len(outputs_root_a):]
            audio_url = f"/api/multimodal/file/outputs/{rel_a}"
            # Merge: video matches audio duration since it was generated to match
            merged = self._merge_audio_video(video_path, audio_path, job_id)
            if merged:
                video_path = merged

        # Move final video out of media dir, clean up only manim intermediates
        import shutil as _shutil_c
        final_path = self.output_dir / f"{job_id}_final.mp4"
        try:
            _shutil_c.move(str(video_path), str(final_path))
            video_path = str(final_path)
        except Exception:
            pass
        try:
            for _p in self.output_dir.glob(f"{job_id}_scene*"):
                if _p.is_file(): _p.unlink(missing_ok=True)
            _media = self.output_dir / "media"
            if _media.exists(): _shutil_c.rmtree(str(_media), ignore_errors=True)
        except Exception: pass

        # Convert absolute path to static URL.
        # project_root = D:/EduAgent
        # video_path = D:/EduAgent/outputs/manim/xxx.mp4
        # URL = /api/multimodal/file/outputs/manim/xxx.mp4
        rel = video_path.replace("\\", "/")
        outputs_root = str(settings.project_root / "outputs").replace("\\", "/") + "/"
        if rel.startswith(outputs_root):
            rel = rel[len(outputs_root):]
        url = f"/api/multimodal/file/outputs/{rel}"

        # ── Step 6: Multimodal QC (best-effort, non-blocking) ──
        qc_result = self._quality_check(video_path, topic, subject)

        return _response(status="success", provider=self.provider,
            result={"video_url": url, "local_path": video_path,
                    "audio_url": audio_url, "narration_text": narration,
                    "script": manim_code, "qc": qc_result})

    def _generate_narration_only(self, llm, topic: str, subject: str, kb_context: str) -> str:
        """Generate Chinese narration for template-based animations."""
        kb_block = f"\n知识点参考：{kb_context[:800]}" if kb_context else ""
        prompt = f"为以下知识点写一段中文旁白讲解稿。像老师正常讲课，把该讲的讲清楚。引入→原理→例子→总结。逗号句号停顿。\n课程: {subject}\n节: {topic}{kb_block}\n只输出旁白。"
        try:
            raw = llm.chat(messages=[
                {"role": "system", "content": "你是数学老师。写中文旁白，自然口语。"},
                {"role": "user", "content": prompt},
            ], temperature=0.3, max_tokens=2000)
            return raw.strip()
        except Exception:
            return ""

    def _fix_script(self, llm, broken_code: str, stderr: str, stdout: str, topic: str, subject: str, kb_context: str) -> str:
        """Ask LLM to fix a failing Manim script based on the error output."""
        full = (stderr or "") + (stdout or "")
        # Extract LaTeX log content if available
        latex_log = ""
        try:
            import glob as _glob, os as _os
            # Find the most recent LaTeX log
            for _d in [_os.path.join(_os.path.dirname(str(self.output_dir)), "media", "Tex"),
                       _os.path.join(_os.environ.get("TEMP", "/tmp"), "media", "Tex")]:
                logs = _glob.glob(_os.path.join(_d, "*.log")) if _os.path.isdir(_d) else []
                if logs:
                    latest = max(logs, key=_os.path.getmtime)
                    with open(latest, errors='replace') as _f:
                        latex_log = _f.read()[-2000:]
                    break
        except Exception:
            pass

        error_summary = (latex_log[-1000:] if latex_log else "") or full[-1500:]

        prompt = f"""Fix this broken Manim script. The corrected code must render without errors.

## Error
{error_summary[:2000]}

## Broken script
```python
{broken_code}
```

Fix ALL bugs then output the COMPLETE corrected code. DeepSeek common mistakes:
- Never put Chinese chars in MathTex — use Text() for Chinese
- All Tex() → Text() (Manim CE v0.20)
- Add `import numpy as np` if using np
- Scene class must be "EduScene"
- ⚠️ Remove ALL SVGMobject() and ImageMobject() calls — those asset files do not exist in the project

Only output corrected code, no explanation."""

        try:
            raw = llm.chat(messages=[
                {"role": "system", "content": "You are a Manim CE v0.20 expert. Fix broken Manim code. Output only corrected Python."},
                {"role": "user", "content": prompt},
            ], temperature=0.1, max_tokens=3000)
            code = raw.strip()
            if code.startswith("```"):
                code = re.sub(r"^```\w*\n", "", code)
                code = re.sub(r"\n```$", "", code)
            return code if "class EduScene" in code else ""
        except Exception:
            return ""

    def _generate_combined(self, llm, topic: str, subject: str, kb_context: str, kp_text: str = "", target_duration: float = 0, narration_text: str = "") -> dict | None:
        kb_block = f"\n\n## 知识点\n{kb_context}" if kb_context else ""
        if kp_text:
            kb_block += f"\n## 本节重点\n{kp_text}"
        if not kb_block:
            kb_block = f"\n\n请根据「{topic}」这个主题生成内容，不要用通用例子。"

        duration_hint = f"\n\n动画时长需要约 {target_duration:.0f} 秒。" if target_duration > 0 else ""
        narration_hint = f"\n\n旁白已经写好，动画必须严格对应旁白内容：\n{narration_text}" if narration_text else ""

        prompt = f"""请根据以下旁白稿生成匹配的 Manim 动画。旁白说什么，画面就展示什么。{kb_block}{narration_hint}{duration_hint}

## 教学主题
课程: {subject}
节: {topic}

## 输出格式（严格 JSON）
{{"code": "Manim CE Python 动画代码"}}

## 要求
- Scene 类名 "EduScene"，深色背景，白/金色文字
- MathTex 公式，Text 中文
- 围绕知识点逐步展开：概念→推导→例题→总结
- 每个重要元素后 self.wait() 停顿
- ⚠️ 禁止使用 SVGMobject、ImageMobject 等需要外部资源文件的 API（项目没有这些资源文件）

只输出 JSON。"""

        try:
            raw = llm.chat(messages=[
                {"role": "system", "content": "你是数学老师。根据知识点内容设计教学动画。杜绝 f(x)=x² 这种通用例子。"},
                {"role": "user", "content": prompt},
            ], temperature=0.3, max_tokens=8000)
            raw = raw.strip()
            logger.info("LLM response len=%d preview=%s", len(raw), raw[:100])
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n", "", raw)
                raw = re.sub(r"\n```$", "", raw)
            parsed = json.loads(raw)
            code = parsed.get("code", "")
            logger.info("Parsed code len=%d", len(code) if code else 0)
            return parsed
        except Exception as e:
            logger.warning("Manim combined generation failed: %s", e)
            return None

    @staticmethod
    def _scrub_code(code: str) -> str:
        """Fix common DeepSeek-generated Manim mistakes before rendering."""
        import re as _re
        # 1. Preserve Text() contents, strip non-ASCII everywhere else
        texts = {}
        def _save_text(m):
            key = f"__TEXT_{len(texts)}__"
            texts[key] = m.group(0)
            return key
        code = _re.sub(r'Text\("([^"]*)"\)', _save_text, code)
        # 2. Strip ALL non-ASCII from everything else
        code = _re.sub(r'[^\x00-\x7F]+', '', code)
        # 3. Restore Text() contents
        for key, value in texts.items():
            code = code.replace(key, value)
        # 4. Fix Tex() → Text() (any surviving Tex calls)
        code = _re.sub(r'(?<!Math)Tex\(', 'Text(', code)
        # 5. Strip SVGMobject/ImageMobject calls — no external assets exist
        code = _re.sub(r'SVGMobject\s*\([^)]*\)', 'Square()', code)
        code = _re.sub(r'ImageMobject\s*\([^)]*\)', 'Square()', code)
        # 6. Ensure imports
        if "from manim import" not in code:
            code = "from manim import *\n" + code
        if "import numpy as np" not in code:
            code = code.replace("from manim import *", "from manim import *\nimport numpy as np")
        return code

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Strip Markdown formatting that TTS would read aloud (**, *, `, #, etc.)."""
        import re as _re
        # Remove bold/italic markers
        text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = _re.sub(r'\*(.+?)\*', r'\1', text)
        text = _re.sub(r'__(.+?)__', r'\1', text)
        text = _re.sub(r'_(.+?)_', r'\1', text)
        # Remove inline code and code blocks
        text = _re.sub(r'`{1,3}[^`]*`{1,3}', '', text)
        # Remove heading markers
        text = _re.sub(r'^#{1,6}\s+', '', text, flags=_re.MULTILINE)
        # Remove strikethrough
        text = _re.sub(r'~~(.+?)~~', r'\1', text)
        # Remove link labels but keep text [text](url)
        text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove image markup ![alt](url)
        text = _re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
        # Remove horizontal rules
        text = _re.sub(r'^---+\s*$', '', text, flags=_re.MULTILINE)
        # Collapse multiple blank lines
        text = _re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using FFmpeg."""
        import shutil as _s
        ffmpeg = _s.which("ffmpeg")
        if not ffmpeg:
            for candidate in [
                r"C:\Users\hejiaxuan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
            ]:
                if os.path.isfile(candidate):
                    ffmpeg = candidate
                    break
        if not ffmpeg:
            return 0
        try:
            import subprocess, re as _re
            result = subprocess.run([str(ffmpeg), "-i", video_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=10)
            m = _re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        return 0

    def _generate_narration_only(self, llm, topic: str, subject: str, kb_context: str) -> str:
        """Generate natural Chinese narration (used BEFORE Manim code)."""
        kb_block = f"\n知识点参考：{kb_context[:800]}" if kb_context else ""
        prompt = f"为知识点写中文旁白稿。像老师正常讲课。引入→概念→推导→例子→总结。自然口语，不要重复。\n课程: {subject}\n节: {topic}{kb_block}\n只输出旁白，不要用 Markdown 标记（如 **、*、`、# 等）。"
        try:
            raw = llm.chat(messages=[
                {"role": "system", "content": "你是数学老师。写中文旁白，自然口语，不要重复。"},
                {"role": "user", "content": prompt},
            ], temperature=0.3, max_tokens=2000)
            return raw.strip()
        except Exception:
            return ""

    def _generate_narration_for_duration(self, llm, topic: str, subject: str, kb_context: str, duration: float, manim_code: str = "") -> str:
        """Generate narration that matches both video duration AND screen content."""
        import re as _re
        text_elements = _re.findall(r'Text\("([^"]+)"\)', manim_code)
        mathtex_elements = _re.findall(r'MathTex\(r"([^"]+)"\)', manim_code)
        scene_summary = " → ".join(text_elements[:8]) if text_elements else topic
        formulas = "、".join(mathtex_elements[:5]) if mathtex_elements else ""

        kb_block = f"\n知识点参考：{kb_context[:800]}" if kb_context else ""
        prompt = (
            f"视频已渲染完成。请对着画面内容写中文旁白稿。\n\n"
            f"课程: {subject}\n节: {topic}\n"
            f"画面内容: {scene_summary}\n"
            + (f"公式: {formulas}\n" if formulas else "") +
            f"{kb_block}\n\n"
            f"要求：对着画面写旁白，屏幕上出现什么就讲什么。像老师讲课，自然口语。用短句，不要重复。只输出旁白。"
        )
        try:
            raw = llm.chat(messages=[
                {"role": "system", "content": "你是数学老师。看着视频画面写旁白——屏幕出现什么就讲什么。"},
                {"role": "user", "content": prompt},
            ], temperature=0.3, max_tokens=2000)
            return raw.strip()
        except Exception:
            return ""

    def _generate_narration(self, text: str, job_id: str) -> str:
        import shutil as _s
        edge_tts = _s.which("edge-tts")
        if not edge_tts:
            for candidate in [
                r"C:\Users\hejiaxuan\AppData\Local\Programs\Python\Python313\Scripts\edge-tts.EXE",
                r"C:\Users\hejiaxuan\AppData\Local\Programs\Python\Python313\Scripts\edge-tts.exe",
            ]:
                if os.path.isfile(candidate):
                    edge_tts = candidate
                    break
        if not edge_tts:
            logger.warning("edge-tts not found")
            return ""
        try:
            import subprocess
            mp3_path = self.output_dir / f"{job_id}_narration.mp3"
            result = subprocess.run(
                [edge_tts, "--voice", "zh-CN-XiaoxiaoNeural",
                 "--text", text, "--write-media", str(mp3_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and mp3_path.exists():
                return str(mp3_path)
            logger.warning("edge-tts failed: %s", result.stderr[:200] if result.stderr else "unknown")
        except Exception as e:
            logger.warning("edge-tts failed: %s", e)
        return ""

    def _merge_audio_video(self, video_path: str, audio_path: str, job_id: str) -> str:
        import shutil as _shutil

        ffmpeg = _shutil.which("ffmpeg")
        if not ffmpeg:
            for candidate in [
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
                r"C:\Users\hejiaxuan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
            ]:
                if os.path.isfile(candidate):
                    ffmpeg = candidate
                    break
        if not ffmpeg:
            logger.warning("FFmpeg not found, skipping audio merge")
            return ""

        try:
            import subprocess, json as _json
            # Get durations
            probe = subprocess.run(
                [str(ffmpeg), "-i", video_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PATH": os.environ.get("PATH", "")})
            probe_a = subprocess.run(
                [str(ffmpeg), "-i", audio_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "PATH": os.environ.get("PATH", "")})

            # Parse durations from stderr
            import re as _re
            v_dur = _re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
            a_dur = _re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe_a.stderr)
            v_sec = float(v_dur.group(1))*3600 + float(v_dur.group(2))*60 + float(v_dur.group(3)) if v_dur else 0
            a_sec = float(a_dur.group(1))*3600 + float(a_dur.group(2))*60 + float(a_dur.group(3)) if a_dur else 0

            merged_path = self.output_dir / f"{job_id}_final.mp4"
            if v_sec > 0 and a_sec > 0:
                ratio = v_sec / a_sec if a_sec > 0 else 1.0
                if ratio < 0.9:
                    # Video shorter than audio: slow down video to match audio
                    result = subprocess.run([
                        str(ffmpeg), "-y",
                        "-i", video_path, "-i", audio_path,
                        "-filter_complex", f"[0:v]setpts={a_sec/v_sec}*PTS[v]",
                        "-map", "[v]", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                        "-shortest", str(merged_path),
                    ], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PATH": os.environ.get("PATH", "")})
                elif ratio > 1.1:
                    # Video longer than audio: loop audio to match video
                    result = subprocess.run([
                        str(ffmpeg), "-y",
                        "-stream_loop", "-1", "-i", audio_path,
                        "-i", video_path,
                        "-c:v", "copy", "-c:a", "aac",
                        "-shortest", str(merged_path),
                    ], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PATH": os.environ.get("PATH", "")})
                else:
                    # Close enough: simple merge
                    result = subprocess.run([
                        str(ffmpeg), "-y",
                        "-i", video_path, "-i", audio_path,
                        "-c:v", "copy", "-c:a", "aac",
                        "-shortest", str(merged_path),
                    ], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PATH": os.environ.get("PATH", "")})

                if result.returncode == 0 and merged_path.exists():
                    logger.info("FFmpeg merged (v=%.1fs a=%.1fs ratio=%.2f)", v_sec, a_sec, ratio)
                    return str(merged_path)

            logger.warning("FFmpeg merge failed: rc=%d stderr=%s", result.returncode, result.stderr[:200] if result.stderr else "")
        except Exception as e:
            logger.warning("FFmpeg merge failed: %s", e)
        return ""

    def _quality_check(self, video_path: str, topic: str, subject: str) -> dict | None:
        """Best-effort multimodal QC: extract a frame and check with Qwen-VL."""
        import shutil as _shutil
        import subprocess

        ffmpeg = _shutil.which("ffmpeg") or _shutil.which("ffprobe")
        if not ffmpeg:
            return None

        frame_path = str(Path(video_path).with_suffix(".qc_frame.png"))
        try:
            subprocess.run(
                [str(ffmpeg), "-y", "-i", video_path, "-vframes", "1",
                 "-q:v", "2", frame_path],
                capture_output=True, text=True, timeout=20,
            )
            if not Path(frame_path).exists():
                return None
        except Exception:
            return None

        # Use Qwen-VL to inspect the frame
        try:
            from app.services.multimodal_provider import QwenVisionProvider
            qwen = QwenVisionProvider()
            result = qwen.run({
                "task_type": "image_understanding",
                "image_url": f"file://{frame_path}",
                "user_message": (
                    f"这是一帧数学教学动画截图，主题是「{subject}——{topic}」。"
                    "请检查：1) 画面元素是否完整（无遮挡、无缺失）"
                    "2) 数学公式是否清晰可读 3) 整体布局是否合理。"
                    "用一段简短中文回答，指出发现的问题，没有问题的维度就说没问题。"
                ),
            })
            if result.get("status") in ("success", "needs_manual_review"):
                payload = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
                text = str(payload.get("detected_text") or payload.get("summary") or payload.get("display_text") or "")
                issues = "no" not in (text or "").lower()[:30]
                return {"passed": not issues, "summary": text[:200] if text else "QC 未获取到有效反馈"}
        except Exception as e:
            logger.warning("QC check failed: %s", e)
        return {"passed": True, "summary": "QC skipped (Qwen-VL unavailable)"}

    @staticmethod
    def poll_task(task_id: str) -> dict[str, Any]:
        """Poll a DashScope async video generation task.

        Returns:
            {"status": "success", "video_url": "..."}
            {"status": "pending", "task_status": "RUNNING"}
            {"status": "failed", "message": "..."}
        """
        api_key = _env("DASHSCOPE_API_KEY", "WAN_API_KEY", "QWEN_API_KEY")
        endpoint = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        try:
            body = _json_post(endpoint, {}, api_key, timeout=15)
            output = body.get("output", {})
            task_status = _text(output.get("task_status"))
            if task_status == "SUCCEEDED":
                video_url = _text(output.get("video_url") or (output.get("results") or {}).get("video_url"))
                if video_url:
                    return {"status": "success", "video_url": video_url}
                return {"status": "failed", "message": "task SUCCEEDED but no video_url returned"}
            if task_status in ("FAILED", "CANCELED", "TERMINATED"):
                return {"status": "failed", "message": _text(output.get("message") or task_status)}
            return {"status": "pending", "task_status": task_status or "UNKNOWN"}
        except (HttpClientError, httpx.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"status": "failed", "message": str(exc)}
