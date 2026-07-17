"""Presenton API provider for PPT generation.

Calls Presenton's REST API to generate professionally formatted PPTX files.
Auto-starts Presenton via Docker when needed.

Environment variables:
  PRESENTON_URL      — Presenton server URL (default: http://localhost:5001)
  PRESENTON_USERNAME — HTTP Basic auth username (default: admin)
  PRESENTON_PASSWORD — HTTP Basic auth password (default: admin)
  DEEPSEEK_API_KEY   — Used when auto-starting Presenton
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "ppt"

DEFAULT_URL = "http://localhost:5001"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin"

_CONTAINER_NAME = "presenton-ai"


class PresentonProvider:
    name = "PresentonProvider"
    provider = "presenton"

    @staticmethod
    def _ping() -> bool:
        """Check if Presenton is reachable."""
        url = os.environ.get("PRESENTON_URL") or DEFAULT_URL
        user = os.environ.get("PRESENTON_USERNAME") or DEFAULT_USER
        pwd = os.environ.get("PRESENTON_PASSWORD") or DEFAULT_PASS
        try:
            resp = requests.get(f"{url}/api/v1/auth/login", auth=(user, pwd), timeout=3)
            return resp.status_code < 500
        except Exception:
            return False

    @staticmethod
    def _find_docker() -> str:
        """Find docker executable path on this system."""
        # Check common install locations
        candidates = [
            "docker",
            "docker.exe",
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
            r"C:\Program Files\Docker\Docker\docker.exe",
        ]
        for cmd in candidates:
            try:
                subprocess.run([cmd, "version"], capture_output=True, timeout=5)
                return cmd
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return ""

    @staticmethod
    def _auto_start() -> bool:
        """Try to start Presenton via Docker."""
        logger.info("Presenton: attempting auto-start via Docker")
        docker_cmd = PresentonProvider._find_docker()
        if not docker_cmd:
            logger.warning("Presenton: Docker not found, cannot auto-start")
            return False

        try:
            subprocess.run([docker_cmd, "info"], capture_output=True, timeout=10)
        except Exception:
            logger.warning("Presenton: Docker engine not ready (still starting?)")
            return False

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            logger.warning("Presenton: DEEPSEEK_API_KEY not set, cannot auto-start")
            api_key = "sk-placeholder"

        # Stop & remove existing container if any
        subprocess.run([docker_cmd, "rm", "-f", _CONTAINER_NAME], capture_output=True, timeout=30)

        try:
            subprocess.run(
                [
                    docker_cmd, "run", "-d",
                    "--name", _CONTAINER_NAME,
                    "-p", "5001:80",
                    "-e", f"DEEPSEEK_API_KEY={api_key}",
                    "-e", "LLM=deepseek",
                    "-e", "IMAGE_PROVIDER=pexels",
                    "-e", "AUTH_USERNAME=admin",
                    "-e", "AUTH_PASSWORD=admin",
                    "-v", f"{_CONTAINER_NAME}_data:/app_data",
                    "ghcr.io/presenton/presenton:latest",
                ],
                capture_output=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Presenton: docker pull/start timed out")
            return False
        except Exception as e:
            logger.warning("Presenton: docker start failed: %s", e)
            return False

        # Wait for it to become ready
        logger.info("Presenton: waiting for service to become ready...")
        for _ in range(30):
            if PresentonProvider._ping():
                logger.info("Presenton: ready")
                return True
            time.sleep(2)

        logger.warning("Presenton: did not become ready after 60s")
        return False

    @staticmethod
    def is_configured() -> bool:
        """Check if Presenton is reachable; attempt auto-start if not."""
        if PresentonProvider._ping():
            return True
        # Try auto-start once
        if PresentonProvider._auto_start():
            return True
        return False

    @staticmethod
    def run(context: dict[str, Any]) -> dict[str, Any]:
        """Generate a PPT via Presenton.

        Context keys:
          topic (str)        — The topic/subject for the presentation.
          difficulty (str)   — easy/medium/hard (maps to verbosity).
          language (str)     — Language code (default: Chinese).

        Returns:
          dict with keys:
            status  — "success" | "failed" | "not_configured"
            result  — {filepath: str, outline: list} on success
        """
        topic = str(context.get("topic") or context.get("user_message") or "").strip()
        if not topic:
            return {"status": "failed", "result": None, "warnings": ["missing topic"]}

        url = os.environ.get("PRESENTON_URL") or DEFAULT_URL
        user = os.environ.get("PRESENTON_USERNAME") or DEFAULT_USER
        pwd = os.environ.get("PRESENTON_PASSWORD") or DEFAULT_PASS

        diff = str(context.get("difficulty", "medium"))
        verbosity = {"easy": "concise", "medium": "standard", "hard": "text-heavy"}.get(diff, "standard")
        lang = str(context.get("language", "Chinese"))

        try:
            logger.info("Presenton: calling API for topic=%s", topic[:60])
            resp = requests.post(
                f"{url}/api/v1/ppt/presentation/generate",
                auth=(user, pwd),
                json={
                    "content": topic,
                    "tone": "educational",
                    "verbosity": verbosity,
                    "language": lang,
                    "export_as": "pptx",
                },
                timeout=300,
            )
            if resp.status_code != 200:
                logger.warning("Presenton API returned %d: %s", resp.status_code, resp.text[:200])
                return {"status": "failed", "result": None, "warnings": [f"API error: {resp.status_code}"]}

            data = resp.json()
            file_path = data.get("path", "")
            if not file_path:
                return {"status": "failed", "result": None, "warnings": ["no path in response"]}

            # Download the PPTX from Presenton
            dl_url = f"{url}{file_path}" if file_path.startswith("/") else file_path
            dl_resp = requests.get(dl_url, auth=(user, pwd), timeout=120)
            if dl_resp.status_code != 200:
                return {"status": "failed", "result": None, "warnings": [f"download failed: {dl_resp.status_code}"]}

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            local_path = str(OUTPUT_DIR / f"presenton_{uuid.uuid4().hex}.pptx")
            with open(local_path, "wb") as f:
                f.write(dl_resp.content)

            logger.info("Presenton: PPT saved to %s (%d bytes)", local_path, len(dl_resp.content))
            return {
                "status": "success",
                "result": {"filepath": local_path, "outline": []},
                "provider": "presenton",
            }

        except requests.Timeout:
            logger.warning("Presenton: request timed out")
            return {"status": "failed", "result": None, "warnings": ["timeout"]}
        except requests.ConnectionError:
            logger.warning("Presenton: connection refused (is the service running?)")
            return {"status": "failed", "result": None, "warnings": ["connection refused"]}
        except Exception as e:
            logger.warning("Presenton: %s", e)
            return {"status": "failed", "result": None, "warnings": [str(e)]}
