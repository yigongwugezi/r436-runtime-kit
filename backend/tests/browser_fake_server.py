"""Start an isolated backend with a local-only PPT generator for browser checks."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path


os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("RAG_ENABLED", "false")
if not os.environ.get("DATABASE_URL"):
    raise SystemExit("DATABASE_URL must point to a temporary SQLite file")

from pptx import Presentation  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import ppt_generator  # noqa: E402
from app.routers import chat_router  # noqa: E402
from app.routers import product  # noqa: E402


def _fake_generate_pptx(topic: str, difficulty: str = "medium", session_id: str = "") -> str:
    output_dir = Path(settings.project_root) / "outputs" / "ppt"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"browser-{uuid.uuid4().hex}.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = topic
    slide.placeholders[1].text = f"Local browser fixture ({difficulty})"
    presentation.save(path)
    return str(path)


ppt_generator.generate_pptx = _fake_generate_pptx


async def _fake_chat_pipeline(**state: object) -> dict[str, object]:
    """Deterministic local-only replies for browser profile-boundary checks."""
    message = str(state.get("user_message") or "")
    profile = state.get("profile_v2") if isinstance(state.get("profile_v2"), dict) else {}
    context = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
    if "年级" in message:
        reply = f"你目前是{context.get('background') or '未记录'}。"
    elif "偏好" in message:
        preferences = "、".join(context.get("resource_preferences") or [])
        reply = f"你偏好通过{preferences or '未记录'}学习。"
    else:
        reply = "已记录当前对话中的明确学习信息。"
    return {"final_reply": reply, "agents_run": ["fake_conversation"], "pipeline_executed": True}


chat_router.run_pipeline = _fake_chat_pipeline

_real_general_resource_generation = product._generate_general_resource


def _delayed_general_resource_generation(*args: object, **kwargs: object) -> dict[str, object]:
    delay_ms = int(os.getenv("EDUAGENT_GENERAL_RESOURCE_DELAY_MS", "0") or 0)
    if delay_ms:
        time.sleep(delay_ms / 1000)
    return _real_general_resource_generation(*args, **kwargs)


product._generate_general_resource = _delayed_general_resource_generation

from app.main import app  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8010")))
