"""DeepTutor wrapper — auto-configures Qwen."""
import os, sys, json, time, threading
from pathlib import Path
from dotenv import load_dotenv
import httpx

root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env")

api_key = os.getenv("LLM_API_KEY", "")
base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

os.environ["DEEPTUTOR_HOME"] = str(root / "runtime_data")
os.environ["OPENAI_API_KEY"] = api_key
os.environ["OPENAI_BASE_URL"] = base_url

catalog = {
    "version": 1,
    "services": {
        "llm": {
            "active_profile_id": "llm-spark",
            "active_model_id": "spark-x",
            "profiles": [{
                "id": "llm-spark", "name": "Spark X",
                "binding": "openai",
                "base_url": base_url,
                "api_key": api_key,
                "models": [{"id": "spark-x", "name": "Spark X", "model": "spark-x"}]
            }]
        }
    }
}

# Pre-write
settings_dir = root / "runtime_data" / "data" / "user" / "settings"
settings_dir.mkdir(parents=True, exist_ok=True)
with open(settings_dir / "model_catalog.json", "w") as f:
    json.dump(catalog, f, indent=2)

def _configure():
    time.sleep(8)
    try:
        r = httpx.post("http://localhost:8000/api/v1/settings/apply", json={"catalog": catalog}, timeout=10)
        print(f"[EduAgent] DeepTutor Qwen configured: {r.status_code}")
    except Exception as e:
        print(f"[EduAgent] Config error: {e}")

threading.Thread(target=_configure, daemon=True).start()

from deeptutor.__main__ import main
sys.argv = ["deeptutor", "serve", "--host", "0.0.0.0", "--port", "8000"]
main()
