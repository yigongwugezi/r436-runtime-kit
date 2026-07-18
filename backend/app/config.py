from pathlib import Path
from importlib.util import find_spec
import logging
import os
import shutil

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)
_skip_env_file = os.getenv("EDUAGENT_SKIP_ENV_FILE") == "1"


def load_backend_env(env_path: Path | None = None) -> bool:
    if _skip_env_file:
        return False
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
    # NOTE: AI credentials (API keys / secrets / app ids) are PER-USER and
    # live in the user_ai_config table (系统设置 → AI 模型配置).  They are
    # intentionally absent from Settings — only technical tuning stays here.
    llm_provider: str = "mock"  # "mock" = test escape hatch; anything else defers to per-user config
    llm_model: str = "deepseek-chat"  # display/tuning only — actual model comes from the user's provider
    llm_temperature: float = 0.2
    llm_enable_search: bool = True
    llm_reasoner_model: str = "deepseek-reasoner"

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

    # ── 学习评估动态阈值 ──────────────────────────────────────────
    mastery_threshold_low: int = 5    # 低分段（<30）调整阈值
    mastery_threshold_mid: int = 8    # 中分段（30-60）
    mastery_threshold_high: int = 12  # 高分段（60-80）
    mastery_threshold_top: int = 15   # 优秀段（>=80）

    # ── 科大讯飞 星火多模态 ──────────────────────────────────────────
    # 凭据（app_id/api_key/api_secret）已迁至每用户配置；仅端点 URL 保留为技术项。
    spark_image_host_url: str = "https://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti"

    # Web search provider settings
    search_provider: str = "mock"       # "mock" | "duckduckgo" | "tavily"（tavily key 为每用户配置）
    search_max_results: int = 5
    search_timeout: int = 10            # seconds for HTTP request
    search_total_timeout: int = 15      # seconds across all real search backends
    search_proxy: str = ""              # optional HTTP/SOCKS proxy for web search only
    search_cache_ttl: int = 300         # in-memory cache TTL in seconds
    search_strategy: str = "free_first_cascade"
    search_provider_timeout_seconds: int = 5
    search_total_timeout_seconds: int = 12
    search_max_provider_calls: int = 8
    search_min_provider_calls_per_type: int = 2
    search_fallback_provider_call_reserve: int = 2
    search_primary_grace_seconds: float = 1.5
    search_provider_hard_timeout_seconds: float = 8.0
    search_total_timeout_single_seconds: float = 12.0
    search_total_timeout_all_seconds: float = 22.0
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
    textbook_max_parse_chars: int = 320000  # max chars sent to LLM for chapter recognition

    model_config = SettingsConfigDict(
        env_file=None if _skip_env_file else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def runtime_capabilities() -> dict[str, object]:
    """Return safe runtime readiness data; credentials and URLs never leave process.

    Credential-based flags are resolved through the **per-user** AI config
    (``app.services.user_ai_config``): inside an authenticated request they
    reflect the current learner's own keys; outside any request context
    (e.g. the unauthenticated ``/health/capabilities`` endpoint) they report
    "not configured", which is accurate — credentials no longer exist at
    process level.  Infrastructure checks (installed deps, manim, RAG) stay
    process-wide.
    """
    from app.services.user_ai_config import user_capabilities

    caps = user_capabilities()
    llm_configured = bool(caps["llmConfigured"])
    search_configured = bool(caps["searchConfigured"])

    def status(configured: bool, dependency: str = "") -> str:
        if configured:
            return "available"
        if dependency and find_spec(dependency) is None:
            return "dependency_missing"
        return "not_configured"

    return {
        "llmProvider": caps["llmProvider"],
        "llmConfigured": llm_configured,
        "searchProvider": caps["searchProvider"],
        "searchConfigured": search_configured,
        "pptConfigured": caps["pptConfigured"],
        "videoConfigured": caps["videoConfigured"],
        "imageConfigured": caps["imageConfigured"],
        "providerStatus": {"llm": status(llm_configured), "search": status(search_configured), "mindmap": status(llm_configured), "ppt": status(bool(caps["pptConfigured"])), "video": status(bool(caps["videoConfigured"]), "manim"), "image": status(bool(caps["imageConfigured"])), "rag": status(bool(settings.rag_enabled), "faiss"), "deeptutor": status(find_spec("deeptutor") is not None and llm_configured), "manim": status(bool(shutil.which("manim")), "manim")},
        "optionalDependencies": {name: find_spec(name) is not None for name in ("ahocorasick", "openai", "faiss", "deeptutor", "manim")},
    }
