from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "eduagent-backend"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"
    llm_provider: str = "mock"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.2
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    database_url: str = "sqlite:///./data/eduagent.db"

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
