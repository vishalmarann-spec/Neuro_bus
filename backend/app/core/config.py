from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Neuro_Bus API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://neurobus:neurobus@localhost:5432/neurobus",
        repr=False,
    )
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    model_provider: str = "disabled"
    model_name: str = ""
    model_api_key: str = Field(default="", repr=False)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
