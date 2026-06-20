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

    database_url: str = "sqlite:///./data/eduagent.db"

    # Agent orchestration settings
    agent_timeout: int = 60  # seconds per individual agent
    agent_run_timeout: int = 300  # seconds for full orchestrator run
    llm_retry_count: int = 2  # number of retries for failed LLM calls
    llm_retry_delay: float = 1.0  # seconds between retries
    llm_request_timeout: int = 60  # seconds for a single LLM HTTP request
    enable_mock_fallback: bool = False  # demo_result fallback is opt-in for local demos only

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
