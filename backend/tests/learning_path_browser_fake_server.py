"""Isolated browser server with a deterministic legacy learning-path fixture."""

from __future__ import annotations

import os

from browser_fake_server import app
from app.routers import product


_FIXTURE = {
    "id": "path-legacy",
    "title": "旧版兼容路径",
    "description": "结构化说明 " * 100,
    "stages": [{
        "stage_id": "legacy-stage",
        "title": "旧数据阶段",
        "chapters": [{
            "chapter_id": "legacy-chapter",
            "title": "旧章节",
            "sections": [{
                "section_id": "legacy-section",
                "title": "旧小节",
                "goal": "验证正确的章节、资源工作区上下文。",
                "status": "available",
            }],
        }],
    }],
}


for route in tuple(product.router.routes):
    if route.path == "/learning-path" and "GET" in route.methods:
        product.router.routes.remove(route)


@product.router.get("/learning-path")
def get_legacy_learning_path(sessionId: str = "", subjectId: str = "") -> dict[str, object]:
    return {"status": "success", "data": {"path": _FIXTURE}, "sessionId": sessionId, "subjectId": subjectId}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8010")))
