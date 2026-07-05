"""DeepTutor wrapper — auto-configures Spark X."""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv

root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env")

api_key = os.getenv("LLM_API_KEY", "")
base_url = os.getenv("LLM_BASE_URL", "https://spark-api-open.xf-yun.com/x2")
model = os.getenv("LLM_MODEL", "spark-x")

os.environ["DEEPTUTOR_HOME"] = str(root / "runtime_data")
os.environ["OPENAI_API_KEY"] = api_key
os.environ["OPENAI_BASE_URL"] = base_url

settings_dir = root / "runtime_data" / "data" / "user" / "settings"
settings_dir.mkdir(parents=True, exist_ok=True)

catalog = {
    "version": 1,
    "services": {
        "llm": {
            "active_profile_id": "llm-spark",
            "active_model_id": "spark-x",
            "profiles": [{
                "id": "llm-spark", "name": "Spark X",
                "binding": "openai",
                "base_url": base_url, "api_key": api_key,
                "models": [{"id": "spark-x", "name": "Spark X", "model": "spark-x"}]
            }]
        }
    }
}
with open(settings_dir / "model_catalog.json", "w") as f:
    json.dump(catalog, f, indent=2)

from deeptutor.__main__ import main
sys.argv = ["deeptutor", "serve", "--host", "0.0.0.0", "--port", "8000"]
main()
