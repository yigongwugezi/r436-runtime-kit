"""
讯飞开放平台 — TTS / ASR / OCR 客户端
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime
from urllib.parse import urlencode
from typing import Any

import httpx

logger = logging.getLogger("xunfei-platform")

TTS_URL = "https://api.xfyun.cn/v1/tts"
ASR_URL = "https://api.xfyun.cn/v1/asr"
OCR_URL = "https://api.xfyun.cn/v1/ocr"


def _build_auth_url(base_url: str, api_key: str, api_secret: str) -> str:
    """构建带鉴权的 WebSocket URL"""
    host = base_url.replace("https://", "").replace("http://", "").split("/")[0]
    path = "/" + "/".join(base_url.replace("https://", "").replace("http://", "").split("/")[1:])
    now = datetime.utcnow()
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()

    authorization = f'api_key="{api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
    return f"{base_url}?{urlencode({'authorization': base64.b64encode(authorization.encode()).decode(), 'date': date, 'host': host})}"


class XunfeiTTS:
    """讯飞 TTS 语音合成"""

    def __init__(
        self,
        app_id: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self.app_id = app_id or os.getenv("XUNFEI_TTS_APP_ID", "")
        self.api_key = api_key or os.getenv("XUNFEI_TTS_API_KEY", "")
        self.api_secret = api_secret or os.getenv("XUNFEI_TTS_API_SECRET", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.app_id) and bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        return self._client

    async def synthesize(
        self,
        text: str,
        voice: str = "xiaoyan",
        speed: int = 50,
        output_format: str = "mp3",
    ) -> bytes | None:
        """
        文本转语音
        Args:
            text: 要合成的文本（单次最多 500 字）
            voice: 发音人 (xiaoyan/xiaofeng/xiaomeng/aisjiuxu 等)
            speed: 语速 0-100
            output_format: 输出格式
        Returns:
            音频二进制数据，失败返回 None
        """
        if not self.configured:
            return None

        client = await self._get_client()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Appid": self.app_id,
            "X-CurTime": str(int(time.time())),
            "X-Param": base64.b64encode(json.dumps({
                "auf": "audio/L16;rate=16000",
                "aue": output_format,
                "voice_name": voice,
                "speed": str(speed),
                "volume": "50",
                "pitch": "50",
                "engine_type": "intp65",
                "text_type": "text",
            }).encode()).decode(),
            "X-CheckSum": "",  # Will be computed
        }

        # 计算 checksum
        raw = self.api_key + headers["X-CurTime"] + headers["X-Param"]
        headers["X-CheckSum"] = hashlib.md5(raw.encode()).hexdigest()

        try:
            resp = await client.post(TTS_URL, headers=headers, data={"text": text[:500]})
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0 and result.get("data", {}).get("audio"):
                return base64.b64decode(result["data"]["audio"])
            logger.error("TTS error: %s", result.get("message", "unknown"))
            return None
        except Exception as exc:
            logger.error("TTS failed: %s", exc)
            return None

    async def generate_lecture_audio(
        self,
        script: str,
        voice: str = "aisjiuxu",
    ) -> list[bytes]:
        """
        生成讲课音频（长文本自动分段）
        Args:
            script: 讲课脚本文本
            voice: 发音人
        Returns:
            音频段落列表
        """
        segments = []
        # 按 400 字切分（留余量）
        for i in range(0, len(script), 400):
            chunk = script[i:i + 400]
            audio = await self.synthesize(chunk, voice=voice)
            if audio:
                segments.append(audio)
        return segments

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class XunfeiASR:
    """讯飞 ASR 语音识别"""

    def __init__(
        self,
        app_id: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.app_id = app_id or os.getenv("XUNFEI_ASR_APP_ID", "")
        self.api_key = api_key or os.getenv("XUNFEI_ASR_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.app_id) and bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def transcribe(self, audio_bytes: bytes, audio_format: str = "mp3") -> str:
        """语音转文字"""
        if not self.configured:
            return ""

        client = await self._get_client()
        headers = {
            "Content-Type": "application/json",
            "X-Appid": self.app_id,
            "X-CurTime": str(int(time.time())),
            "X-Param": base64.b64encode(json.dumps({
                "engine_type": "sms16k",
                "aue": audio_format,
            }).encode()).decode(),
        }
        raw_data = self.api_key + headers["X-CurTime"] + headers["X-Param"]
        headers["X-CheckSum"] = hashlib.md5(raw_data.encode()).hexdigest()

        try:
            audio_b64 = base64.b64encode(audio_bytes).decode()
            resp = await client.post(ASR_URL, headers=headers, json={"audio": audio_b64})
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("text", "")
            logger.error("ASR error: %s", result.get("message", "unknown"))
            return ""
        except Exception as exc:
            logger.error("ASR failed: %s", exc)
            return ""

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class XunfeiOCR:
    """讯飞 OCR 图片识别"""

    def __init__(
        self,
        app_id: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.app_id = app_id or os.getenv("XUNFEI_OCR_APP_ID", "")
        self.api_key = api_key or os.getenv("XUNFEI_OCR_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.app_id) and bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def extract_text(self, image_bytes: bytes) -> str:
        """图片转文字"""
        if not self.configured:
            return ""

        client = await self._get_client()
        headers = {
            "Content-Type": "application/json",
            "X-Appid": self.app_id,
            "X-CurTime": str(int(time.time())),
            "X-Param": base64.b64encode(json.dumps({"engine_type": "print"}).encode()).decode(),
        }
        raw_data = self.api_key + headers["X-CurTime"] + headers["X-Param"]
        headers["X-CheckSum"] = hashlib.md5(raw_data.encode()).hexdigest()

        try:
            image_b64 = base64.b64encode(image_bytes).decode()
            resp = await client.post(OCR_URL, headers=headers, json={"image": image_b64})
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("text", "")
            logger.error("OCR error: %s", result.get("message", "unknown"))
            return ""
        except Exception as exc:
            logger.error("OCR failed: %s", exc)
            return ""

    async def extract_question_from_image(self, image_bytes: bytes) -> dict[str, Any]:
        """
        从图片中提取题目信息（拍照搜题场景）
        返回：{question_text, options, knowledge_points}
        """
        text = await self.extract_text(image_bytes)
        if not text:
            return {"question_text": "", "options": [], "knowledge_points": []}

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        question_text = lines[0] if lines else ""
        options = [line for line in lines[1:] if len(line) < 4 or line[0] in "ABCDabcd①②③④"]
        return {
            "question_text": question_text,
            "options": options,
            "knowledge_points": [],
            "raw_text": text,
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
