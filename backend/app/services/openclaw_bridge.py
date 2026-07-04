"""OpenClaw bridge — Python → Node.js OpenClaw orchestration engine."""
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
load_dotenv(_env)

logger = logging.getLogger(__name__)
OPENCLAW_URL = os.getenv("OPENCLAW_URL", "http://localhost:8400")


def process_message(message: str, session_id: str) -> dict[str, Any]:
    """Send message to OpenClaw, return orchestrated result."""
    try:
        with httpx.Client(timeout=180) as c:
            r = c.post(f"{OPENCLAW_URL}/process", json={
                "message": message,
                "session_id": session_id,
            })
            if r.status_code == 200:
                return r.json()
            logger.warning("OpenClaw returned %d: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("OpenClaw bridge failed: %s", e)
    return {"workflow": "fallback", "results": {}, "events": []}


def process_message_stream(message: str, session_id: str):
    """SSE stream from OpenClaw — yields events as dicts."""
    try:
        with httpx.Client(timeout=300) as c:
            with c.stream("POST", f"{OPENCLAW_URL}/process/stream", json={
                "message": message,
                "session_id": session_id,
            }) as r:
                for line in r.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            yield json.loads(data_str)
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        logger.warning("OpenClaw stream failed: %s", e)
        yield {"status": "error", "error": str(e)}


def check_health() -> dict:
    """Check if OpenClaw is reachable."""
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{OPENCLAW_URL}/health")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return {"status": "unreachable"}
