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
from urllib import error, request

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


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _json_post(url: str, payload: dict[str, Any], api_key: str, timeout: int = 60) -> dict[str, Any]:
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _data_url_from_base64(value: str) -> str:
    value = _text(value)
    if value.startswith("data:image/"):
        return value
    return f"data:image/png;base64,{value}"


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


def image_input_from_context(context: dict[str, Any]) -> str:
    if _text(context.get("image_url")):
        return _text(context.get("image_url"))
    if _text(context.get("image_base64")):
        return _data_url_from_base64(_text(context.get("image_base64")))
    for item in context.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        for key in ("image_url", "url"):
            if _text(item.get(key)):
                return _text(item.get(key))
        if _text(item.get("image_base64")):
            return _data_url_from_base64(_text(item.get("image_base64")))
        local = _resolve_upload_path(_text(item.get("local_path")))
        if local and local.exists():
            mime = mimetypes.guess_type(local.name)[0] or "image/png"
            return f"data:{mime};base64,{base64.b64encode(local.read_bytes()).decode('ascii')}"
    return ""


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
    return {
        "image_type": _text(parsed.get("image_type")) or "unknown",
        "subject": _text(parsed.get("subject")) or "unknown",
        "detected_text": _text(parsed.get("detected_text")),
        "question_text": _text(parsed.get("question_text")),
        "student_answer": _text(parsed.get("student_answer")),
        "formula_text": _text(parsed.get("formula_text")),
        "diagram_description": _text(parsed.get("diagram_description")),
        "possible_knowledge_points": parsed.get("possible_knowledge_points") if isinstance(parsed.get("possible_knowledge_points"), list) else [],
        "summary": _text(parsed.get("summary")) or raw_text[:500],
        "confidence": float(parsed.get("confidence") or 0.5),
        "needs_manual_review": bool(parsed.get("needs_manual_review", False)),
    }


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
        image = image_input_from_context(context)
        if not api_key:
            return _response(status="provider_not_configured", provider=self.provider, warnings=["Qwen vision provider is not configured."], trace={"required_env": ["DASHSCOPE_API_KEY or QWEN_API_KEY"]})
        if not image:
            return _response(status="needs_input", provider=self.provider, warnings=["missing image input"], trace={"input_keys": sorted(context.keys())})

        prompt = (
            "Analyze this learning image. Return JSON only with keys: "
            "image_type, subject, detected_text, question_text, student_answer, formula_text, "
            "diagram_description, possible_knowledge_points, summary, confidence, needs_manual_review."
        )
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
        try:
            body = self.post_json(f"{base_url}/chat/completions", payload, api_key, int(os.getenv("QWEN_TIMEOUT", "60")))
            raw_text = _text(body.get("choices", [{}])[0].get("message", {}).get("content"))
            try:
                parsed = parse_safe(raw_text)
                status = "success"
            except Exception:
                parsed = {}
                status = "partial_success"
            return _response(
                status=status,
                provider=self.provider,
                result=_normalize_vision_result(parsed, raw_text),
                trace={"model": model, "base_url": base_url},
            ) | {"model": model, "raw_text": raw_text}
        except (error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            return _response(status="failed", provider=self.provider, warnings=[str(exc)], trace={"model": model, "base_url": base_url})


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
