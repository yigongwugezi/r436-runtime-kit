from pathlib import Path
import logging
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def load_backend_env(env_path: Path | None = None) -> bool:
    path = env_path or (Path(__file__).resolve().parents[1] / ".env")
    if not path.exists():
        logger.info("Backend env file missing: %s", path)
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)
    logger.info("Backend env file loaded: %s", path)
    return True


load_backend_env()


class Settings(BaseSettings):
    app_name: str = "r436-runtime-kit-backend"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"
    llm_provider: str = "mock"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.2
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    database_url: str = "sqlite:///./data/r436_runtime.db"

    # ── 路径规划细粒度控制 ──
    path_max_tokens: int = 12000      # 路径生成 LLM 最大输出 token 数，越大越详细
    path_sections_per_day: float = 3.0  # 每天生成的小节数，越大越细
    lecture_max_tokens: int = 16384   # 讲义生成 LLM 最大输出 token 数

    # Agent orchestration settings
    agent_timeout: int = 3600  # 1 hour, effectively no timeout for batch generation
    agent_run_timeout: int = 300  # seconds for full orchestrator run
    llm_retry_count: int = 2  # number of retries for failed LLM calls
    llm_retry_delay: float = 1.0  # seconds between retries
    llm_request_timeout: int = 120  # seconds for a single LLM HTTP request
    enable_mock_fallback: bool = False  # demo_result fallback is opt-in for local demos only

    # Learning event deduplication
    event_dedup_view_window_seconds: int = 300  # 5-minute window for resource_view dedup

    # ── 科大讯飞 星火多模态 ──────────────────────────────────────────
    spark_app_id: str = ""
    spark_api_key: str = ""
    spark_api_secret: str = ""
    spark_image_host_url: str = "https://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti"
    spark_vision_app_id: str = ""
    spark_vision_api_key: str = ""
    spark_vision_api_secret: str = ""
    # Qwen / DashScope
    qwen_api_key: str = ""
    qwen_base_url: str = ""
    qwen_vl_model: str = ""
    qwen_image_model: str = ""
    # Wan Video
    wan_api_key: str = ""
    wan_video_model: str = ""

    # Web search provider settings
    search_provider: str = "mock"       # "mock" | "duckduckgo" | "tavily"
    tavily_api_key: str = ""
    search_max_results: int = 5
    search_timeout: int = 10            # seconds for HTTP request
    search_total_timeout: int = 15      # seconds across all real search backends
    search_proxy: str = ""              # optional HTTP/SOCKS proxy for web search only
    search_cache_ttl: int = 300         # in-memory cache TTL in seconds
    search_strategy: str = "free_first_cascade"
    search_provider_timeout_seconds: int = 5
    search_total_timeout_seconds: int = 12
    search_max_provider_calls: int = 8
    search_primary_grace_seconds: float = 1.5
    search_provider_hard_timeout_seconds: float = 3.5
    search_total_timeout_single_seconds: float = 8.0
    search_total_timeout_all_seconds: float = 10.0
    search_max_concurrent_providers: int = 2
    search_min_results_single_type: int = 6
    search_max_results_single_type: int = 8
    search_min_results_all: int = 8
    search_max_results_all: int = 12
    search_min_types_all: int = 3
    search_cache_enabled: bool = True
    search_cache_ttl_seconds: int = 21600
    search_stale_cache_seconds: int = 604800
    search_cache_max_entries: int = 500
    search_circuit_failure_threshold: int = 3
    search_circuit_open_seconds: int = 60
    search_dynamic_provider_order_enabled: bool = True
    search_reset_client_on_network_error: bool = True

    # In-process long-running workflow progress (temporary state only)
    workflow_task_ttl_seconds: int = 1800
    workflow_task_max_entries: int = 500
    workflow_event_buffer_max: int = 200
    workflow_preview_max_chars: int = 12000
    workflow_progress_event_throttle_ms: int = 100
    workflow_max_concurrent_tasks_per_user: int = 3
    workflow_heartbeat_seconds: int = 15

    # ── RAG / Vector Search ───────────────────────────────────────────
    rag_enabled: bool = True
    """When False the RAG router is not registered and the query engine
    returns empty results — useful for development without a built RAG DB."""

    rag_index_path: str = "./data/faiss/eduagent_knowledge.faiss"
    """FAISS index file path for persistent vector storage."""

    hf_home: str = "./data/huggingface_cache"
    """HuggingFace model cache directory (overrides ``HF_HOME`` env var at runtime)."""

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    # ── Textbook Import ──────────────────────────────────────────────
    textbook_storage_path: str = "./data/textbooks"
    textbook_max_upload_size: int = 100 * 1024 * 1024  # 100 MB
    textbook_max_parse_chars: int = 80000  # max chars sent to LLM for chapter recognition

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
