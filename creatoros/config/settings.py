"""Application settings for CreatorOS."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration values loaded from environment variables and the project .env file."""

    app_name: str = Field(default="CreatorOS", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="sqlite:///./database/creatoros.db",
        alias="DATABASE_URL",
    )
    default_llm_provider: str = Field(default="mock", alias="DEFAULT_LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    youtube_client_id: str | None = Field(default=None, alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str | None = Field(default=None, alias="YOUTUBE_CLIENT_SECRET")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
