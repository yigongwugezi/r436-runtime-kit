"""讯飞智文 (iFlytek) PPT generation API provider.

Calls 讯飞智文 PPT API to generate professionally formatted PPTX with templates.
No Docker required — pure HTTP API.

Environment variables:
  AIPPT_APP_ID     — 讯飞智文应用 ID
  AIPPT_API_SECRET — 讯飞智文 API 密钥
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

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "ppt"

_BASE_URL = "https://zwapi.xfyun.cn"
_MAX_POLL_SECONDS = 300  # 5 min max wait
_POLL_INTERVAL = 3       # check every 3s


def _extract_preview(detail_image: str) -> str:
    """Extract a preview image URL from the detailImage JSON string."""
    try:
        info = json.loads(detail_image) if detail_image else {}
        return info.get("titleCoverImageLarge") or info.get("titleCoverImage") or ""
    except (json.JSONDecodeError, TypeError):
        return ""


class IflytekPPTProvider:
    name = "IflytekPPTProvider"
    provider = "iflytek_ppt"

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("AIPPT_APP_ID")) and bool(os.environ.get("AIPPT_API_SECRET"))

    @staticmethod
    def _sign(ts: int) -> str:
        app_id = os.environ.get("AIPPT_APP_ID", "")
        secret = os.environ.get("AIPPT_API_SECRET", "")
        auth = hashlib.md5((app_id + str(ts)).encode()).hexdigest()
        return base64.b64encode(
            hmac.new(secret.encode(), auth.encode(), hashlib.sha1).digest()
        ).decode()

    @staticmethod
    def _headers(content_type: str = "application/json; charset=utf-8") -> dict:
        ts = int(time.time())
        return {
            "appId": os.environ["AIPPT_APP_ID"],
            "timestamp": str(ts),
            "signature": IflytekPPTProvider._sign(ts),
            "Content-Type": content_type,
        }

    @staticmethod
    def get_template_list(pay_type: str = "free", page_size: int = 20) -> list[dict]:
        """Fetch available PPT templates (multi-page, API caps at ~10/page)."""
        if not IflytekPPTProvider.is_configured():
            return []
        all_records: list[dict] = []
        seen: set[str] = set()
        for page in range(1, 6):  # up to 5 pages → ~50 templates
            try:
                resp = requests.get(
                    f"{_BASE_URL}/api/ppt/v2/template/list",
                    headers=IflytekPPTProvider._headers(),
                    params={"payType": pay_type, "pageNum": page, "pageSize": 10},
                    timeout=10,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                records = data.get("data", {}).get("records", [])
                if not records:
                    break
                for r in records:
                    tid = r.get("templateIndexId", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        all_records.append({
                            "templateId": tid,
                            "name": f"{r.get('industry', '通用')} · {r.get('style', '标准')}",
                            "style": r.get("style", ""),
                            "color": r.get("color", ""),
                            "preview": _extract_preview(r.get("detailImage", "")),
                        })
                if len(records) < 10:
                    break  # last page
            except Exception:
                break
        return all_records[:page_size]

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
    def run(context: dict[str, Any], on_progress: Any = None) -> dict[str, Any]:
        """Generate a PPT via 讯飞智文 API.

        Context keys:
          topic (str)  — The topic/subject for the presentation.
          template_id (str) — Optional template ID.

        on_progress — Optional callback(label: str, stage: str, meta: dict) for workflow events.

        Returns:
          dict with keys:
            status — "success" | "failed"
            result — {filepath: str} on success
        """
        topic = str(context.get("topic") or "").strip()
        if not topic:
            return {"status": "failed", "result": None, "warnings": ["missing topic"]}

        if not IflytekPPTProvider.is_configured():
            return {"status": "failed", "result": None, "warnings": ["AIPPT_APP_ID or AIPPT_API_SECRET not set"]}

        # Get template
        template_id = context.get("template_id") or IflytekPPTProvider._get_free_template()
        if not template_id:
            return {"status": "failed", "result": None, "warnings": ["no template available"]}

        def _progress(label: str, stage: str = "ppt_generation", **meta: Any) -> None:
            if on_progress:
                try:
                    on_progress(label, stage, meta)
                except Exception:
                    pass

        # Create task
        try:
            _progress("正在创建PPT任务…", "creating")
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
            _progress("讯飞智文正在生成PPT…", "generating", poll_seconds=_MAX_POLL_SECONDS)
            deadline = time.time() + _MAX_POLL_SECONDS
            last_progress_at = time.time()
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
                info = data.get("data", {})
                ppt_status = str(info.get("pptStatus") or "").lower()
                # Push periodic progress (time-based, since API doesn't expose page counts)
                now = time.time()
                if now - last_progress_at >= 5:  # every 5s
                    elapsed = now - (deadline - _MAX_POLL_SECONDS)
                    pct = min(99, int(elapsed / _MAX_POLL_SECONDS * 100))
                    _progress(f"讯飞智文生成中…{pct}%", "generating", completed_units=pct, total_units=100)
                    last_progress_at = now
                if ppt_status in ("done", "success", "completed") or info.get("pptUrl"):
                    download_url = data.get("data", {}).get("pptUrl") or data.get("data", {}).get("downloadUrl")
                    if download_url:
                        # Download the PPTX
                        _progress("正在下载PPT文件…", "downloading")
                        dl = requests.get(download_url, timeout=120)
                        if dl.status_code == 200:
                            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                            local = str(OUTPUT_DIR / f"iflytek_{uuid.uuid4().hex}.pptx")
                            with open(local, "wb") as f:
                                f.write(dl.content)
                            logger.info("Iflytek: PPT saved to %s", local)
                            return {"status": "success", "result": {"filepath": local}, "provider": "iflytek_ppt"}
                    return {"status": "failed", "result": None, "warnings": ["download URL not found"]}
                elif ppt_status in ("failed", "error"):
                    return {"status": "failed", "result": None, "warnings": [f"task failed (status={status})"]}
                # else status 0 or 1 or 2 → still running
            return {"status": "failed", "result": None, "warnings": ["timeout"]}
        except Exception as e:
            return {"status": "failed", "result": None, "warnings": [f"poll failed: {e}"]}
