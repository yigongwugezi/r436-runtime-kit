from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Agent orchestration settings
    agent_timeout: int = 120  # seconds per individual agent
    agent_run_timeout: int = 300  # seconds for full orchestrator run
    llm_retry_count: int = 2  # number of retries for failed LLM calls
    llm_retry_delay: float = 1.0  # seconds between retries
    llm_request_timeout: int = 120  # seconds for a single LLM HTTP request
    enable_mock_fallback: bool = False  # demo_result fallback is opt-in for local demos only

    # Learning event deduplication
    event_dedup_view_window_seconds: int = 300  # 5-minute window for resource_view dedup

    # Web search provider settings
    search_provider: str = "mock"       # "mock" | "duckduckgo" | "tavily"
    tavily_api_key: str = ""
    search_max_results: int = 5
    search_timeout: int = 10            # seconds for HTTP request
    search_cache_ttl: int = 300         # in-memory cache TTL in seconds

    # ── RAG / Vector Search ───────────────────────────────────────────
    rag_enabled: bool = True
    """When False the RAG router is not registered and the query engine
    returns empty results — useful for development without a built RAG DB."""

    rag_index_path: str = "./data/faiss/eduagent_knowledge.faiss"
    """FAISS index file path for persistent vector storage."""

    hf_home: str = "./data/huggingface_cache"
    """HuggingFace model cache directory (overrides ``HF_HOME`` env var at runtime)."""

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
