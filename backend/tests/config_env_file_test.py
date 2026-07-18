"""Configuration imports must be safe without a local .env file."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _env(database_url: str, key: str = "") -> dict[str, str]:
    values = {
        "PATH": os.environ["PATH"],
        "SYSTEMROOT": os.environ["SYSTEMROOT"],
        "WINDIR": os.environ["WINDIR"],
        "APPDATA": os.environ["APPDATA"],
        "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
        "USERPROFILE": os.environ["USERPROFILE"],
        "HOMEDRIVE": os.environ["HOMEDRIVE"],
        "HOMEPATH": os.environ["HOMEPATH"],
        "TEMP": os.environ["TEMP"],
        "TMP": os.environ["TMP"],
        "PYTHONPATH": str(ROOT),
        "EDUAGENT_SKIP_ENV_FILE": "1",
        "DATABASE_URL": database_url,
        "LLM_PROVIDER": "mock",
    }
    if key:
        values["DEEPSEEK_API_KEY"] = key
    return values


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'config-test.db'}"
        code = (
            "from pathlib import Path\n"
            "import app.config as config\n"
            "assert config.settings.database_url == " + repr(database_url) + "\n"
            # v1.1.0: credentials are per-user (user_ai_config table) — Settings
            # must NOT expose any credential field even when the env var is set.
            "assert not hasattr(config.settings, 'deepseek_api_key')\n"
            "assert not hasattr(config.settings, 'tavily_api_key')\n"
            "assert not hasattr(config.settings, 'qwen_api_key')\n"
            "config._skip_env_file = False\n"
            "assert config.load_backend_env(Path(" + repr(str(Path(temp_dir) / 'missing.env')) + ")) is False\n"
            "print('config env test: ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=temp_dir,
            env=_env(database_url, "synthetic-test-key"),
            capture_output=True,
            text=True,
            check=False,
        )
        missing_key = subprocess.run(
            [sys.executable, "-c", "from app.config import settings; assert not hasattr(settings, 'deepseek_api_key'); print('missing provider: ok')"],
            cwd=temp_dir,
            env=_env(database_url),
            capture_output=True,
            text=True,
            check=False,
        )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "synthetic-test-key" not in output
    assert "config env test: ok" in output
    assert missing_key.returncode == 0, missing_key.stdout + missing_key.stderr
    print("config env file: PASS")


if __name__ == "__main__":
    main()
