"""
讯飞 SeeDance 多模态视频生成客户端
支持文生视频、图生视频、分镜脚本生成
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("seedance-client")

SEEDANCE_BASE = "https://api.xf-yun.com/v1/seedance"


class SeeDanceClient:
    """讯飞 SeeDance 视频生成客户端"""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SEEDANCE_API_KEY", "")
        self.api_secret = api_secret or os.getenv("SEEDANCE_API_SECRET", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        return self._client

    async def _request(self, endpoint: str, payload: dict) -> dict:
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = await client.post(f"{SEEDANCE_BASE}/{endpoint}", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def generate_educational_video(
        self,
        topic: str,
        duration_seconds: int = 180,
        style: str = "animated_explainer",
        key_points: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        生成教育视频
        Args:
            topic: 视频主题
            duration_seconds: 视频时长（秒）
            style: 视频风格 (animated_explainer/whiteboard/lecture_slides)
            key_points: 关键知识点列表
        """
        if not self.configured:
            return {"status": "unconfigured", "message": "SeeDance API not configured"}

        payload = {
            "topic": topic,
            "duration": duration_seconds,
            "style": style,
            "key_points": key_points or [],
            "language": "zh",
            "output_format": "mp4",
        }
        try:
            result = await self._request("text_to_video", payload)
            logger.info("SeeDance video generation submitted: %s", result.get("task_id"))
            return {"status": "submitted", "task_id": result.get("task_id"), "estimated_time": result.get("estimated_time", 120)}
        except Exception as exc:
            logger.error("SeeDance video generation failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def generate_storyboard(
        self,
        topic: str,
        script: str,
        scenes: int = 6,
    ) -> dict[str, Any]:
        """生成教育视频分镜脚本"""
        if not self.configured:
            return {"status": "unconfigured", "message": "SeeDance API not configured"}

        payload = {
            "topic": topic,
            "script": script,
            "scenes": scenes,
            "format": "storyboard",
        }
        try:
            result = await self._request("storyboard", payload)
            return {"status": "completed", "storyboard": result.get("storyboard", []), "scenes": scenes}
        except Exception as exc:
            logger.error("SeeDance storyboard failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def query_task(self, task_id: str) -> dict[str, Any]:
        """查询视频生成任务状态"""
        try:
            result = await self._request(f"tasks/{task_id}", {})
            return {
                "task_id": task_id,
                "status": result.get("status", "unknown"),
                "progress": result.get("progress", 0),
                "video_url": result.get("video_url"),
            }
        except Exception as exc:
            logger.error("SeeDance task query failed: %s", exc)
            return {"task_id": task_id, "status": "error", "error": str(exc)}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
