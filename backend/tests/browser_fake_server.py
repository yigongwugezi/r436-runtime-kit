"""Start an isolated backend with a local-only PPT generator for browser checks."""

from __future__ import annotations

import os
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

from app.main import app  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8010")))
