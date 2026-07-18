"""讯飞智文 (iFlytek) PPT generation API provider.

Calls 讯飞智文 PPT API to generate professionally formatted PPTX with templates.
No Docker required — pure HTTP API.

Credentials (per-user, 系统设置 → AI 模型配置):
  aippt.appId     — 讯飞智文应用 ID
  aippt.apiSecret — 讯飞智文 API 密钥
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from app.services.user_ai_config import get_credential

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "ppt"

_BASE_URL = "https://zwapi.xfyun.cn"
_MAX_POLL_SECONDS = 300  # 5 min max wait
_POLL_INTERVAL = 3       # check every 3s


class IflytekPPTProvider:
    name = "IflytekPPTProvider"
    provider = "iflytek_ppt"

    @staticmethod
    def is_configured() -> bool:
        return bool(get_credential("aippt", "appId")) and bool(get_credential("aippt", "apiSecret"))

    @staticmethod
    def _sign(ts: int) -> str:
        app_id = get_credential("aippt", "appId")
        secret = get_credential("aippt", "apiSecret")
        auth = hashlib.md5((app_id + str(ts)).encode()).hexdigest()
        return base64.b64encode(
            hmac.new(secret.encode(), auth.encode(), hashlib.sha1).digest()
        ).decode()

    @staticmethod
    def _headers(content_type: str = "application/json; charset=utf-8") -> dict:
        ts = int(time.time())
        return {
            "appId": get_credential("aippt", "appId"),
            "timestamp": str(ts),
            "signature": IflytekPPTProvider._sign(ts),
            "Content-Type": content_type,
        }

    @staticmethod
    def get_template_list(pay_type: str = "free", page_size: int = 20) -> list[dict]:
        """Fetch available PPT templates."""
        if not IflytekPPTProvider.is_configured():
            return []
        try:
            resp = requests.get(
                f"{_BASE_URL}/api/ppt/v2/template/list",
                headers=IflytekPPTProvider._headers(),
                params={"payType": pay_type, "pageNum": 1, "pageSize": page_size},
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("data", {}).get("list", [])
        except Exception as e:
            logger.warning("Iflytek: get template list failed: %s", e)
            return []

    @staticmethod
    def _get_free_template() -> str | None:
        """Get the first free template ID."""
        templates = IflytekPPTProvider.get_template_list(pay_type="free", page_size=5)
        if templates:
            tid = templates[0].get("templateId")
            logger.info("Iflytek: using template %s", tid)
            return tid
        return None

    @staticmethod
    def run(context: dict[str, Any]) -> dict[str, Any]:
        """Generate a PPT via 讯飞智文 API.

        Context keys:
          topic (str)  — The topic/subject for the presentation.

        Returns:
          dict with keys:
            status — "success" | "failed"
            result — {filepath: str} on success
        """
        topic = str(context.get("topic") or "").strip()
        if not topic:
            return {"status": "failed", "result": None, "warnings": ["missing topic"]}

        if not IflytekPPTProvider.is_configured():
            return {"status": "failed", "result": None, "warnings": ["讯飞智文 PPT 未配置，请在「系统设置 → AI 模型配置」填写 AIPPT 应用 ID 与密钥"]}

        # Get template
        template_id = context.get("template_id") or IflytekPPTProvider._get_free_template()
        if not template_id:
            return {"status": "failed", "result": None, "warnings": ["no template available"]}

        # Create task
        try:
            logger.info("Iflytek: creating PPT task for topic=%s", topic[:60])
            form_data = {
                "query": topic,
                "templateId": template_id,
                "isCardNote": "True",
                "isFigure": "True",
                "aiImage": "normal",
            }
            # Use multipart form data like the MCP server does
            from requests_toolbelt.multipart.encoder import MultipartEncoder
            encoder = MultipartEncoder(fields=form_data)
            headers = IflytekPPTProvider._headers(encoder.content_type)
            resp = requests.post(
                f"{_BASE_URL}/api/ppt/v2/create",
                data=encoder, headers=headers, timeout=30,
            )
            if resp.status_code != 200:
                return {"status": "failed", "result": None, "warnings": [f"create failed: {resp.status_code}"]}
            body = resp.json()
            if body.get("code") != 0:
                return {"status": "failed", "result": None, "warnings": [body.get("message", "create failed")]}
            sid = body["data"]["sid"]
            logger.info("Iflytek: task created, sid=%s", sid)
        except Exception as e:
            return {"status": "failed", "result": None, "warnings": [f"create task failed: {e}"]}

        # Poll for completion
        try:
            deadline = time.time() + _MAX_POLL_SECONDS
            while time.time() < deadline:
                time.sleep(_POLL_INTERVAL)
                resp = requests.get(
                    f"{_BASE_URL}/api/ppt/v2/progress",
                    headers=IflytekPPTProvider._headers(),
                    params={"sid": sid},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                status = data.get("data", {}).get("status")
                if status == 3:  # completed
                    download_url = data.get("data", {}).get("pptUrl") or data.get("data", {}).get("downloadUrl")
                    if download_url:
                        # Download the PPTX
                        dl = requests.get(download_url, timeout=120)
                        if dl.status_code == 200:
                            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                            local = str(OUTPUT_DIR / f"iflytek_{uuid.uuid4().hex}.pptx")
                            with open(local, "wb") as f:
                                f.write(dl.content)
                            logger.info("Iflytek: PPT saved to %s", local)
                            return {"status": "success", "result": {"filepath": local}, "provider": "iflytek_ppt"}
                    return {"status": "failed", "result": None, "warnings": ["download URL not found"]}
                elif status in (4, 5):  # failed
                    return {"status": "failed", "result": None, "warnings": [f"task failed (status={status})"]}
                # else status 0 or 1 or 2 → still running
            return {"status": "failed", "result": None, "warnings": ["timeout"]}
        except Exception as e:
            return {"status": "failed", "result": None, "warnings": [f"poll failed: {e}"]}
