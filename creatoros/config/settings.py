"""Application settings for CreatorOS."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = PROJECT_ROOT / ".env"
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Configuration values loaded from environment variables and the project root .env file."""

    app_name: str = Field(default="CreatorOS", alias="APP_NAME")
    app_env: Literal["development", "testing", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_dev",
        alias="DATABASE_URL",
    )
    default_llm_provider: str = Field(default="mock", alias="DEFAULT_LLM_PROVIDER")
    default_llm_model: str = Field(default="mock-model", alias="DEFAULT_LLM_MODEL")
    default_image_provider: str = Field(default="mock", alias="DEFAULT_IMAGE_PROVIDER")
    default_image_model: str | None = Field(default=None, alias="DEFAULT_IMAGE_MODEL")
    default_tts_provider: str = Field(default="mock", alias="DEFAULT_TTS_PROVIDER")
    default_tts_model: str | None = Field(default=None, alias="DEFAULT_TTS_MODEL")
    default_tts_voice: str = Field(default="alloy", alias="DEFAULT_TTS_VOICE")
    default_video_provider: str = Field(default="mock", alias="DEFAULT_VIDEO_PROVIDER")
    default_video_model: str | None = Field(default=None, alias="DEFAULT_VIDEO_MODEL")
    default_render_provider: str = Field(default="mock", alias="DEFAULT_RENDER_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    kling_api_key: str | None = Field(default=None, alias="KLING_API_KEY")
    kling_api_base_url: str = Field(
        default="https://api-singapore.klingai.com",
        alias="KLING_API_BASE_URL",
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    youtube_client_id: str | None = Field(default=None, alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str | None = Field(default=None, alias="YOUTUBE_CLIENT_SECRET")
    provider_timeout_seconds: float = Field(default=30.0, alias="PROVIDER_TIMEOUT_SECONDS")
    openai_image_timeout_seconds: float = Field(
        default=300.0,
        alias="OPENAI_IMAGE_TIMEOUT_SECONDS",
    )
    kling_video_timeout_seconds: float = Field(
        default=900.0,
        alias="KLING_VIDEO_TIMEOUT_SECONDS",
    )
    kling_video_poll_interval_seconds: float = Field(
        default=5.0,
        alias="KLING_VIDEO_POLL_INTERVAL_SECONDS",
    )
    provider_max_retries: int = Field(default=3, alias="PROVIDER_MAX_RETRIES")
    ffmpeg_path: Path | None = Field(default=None, alias="FFMPEG_PATH")
    caption_font_name: str = Field(default="Arial", alias="CAPTION_FONT_NAME")
    caption_font_file: Path | None = Field(default=None, alias="CAPTION_FONT_FILE")
    artifact_root: Path = Field(default=PROJECT_ROOT / "artifacts", alias="ARTIFACT_ROOT")
    assets_dir: Path = Field(default=PROJECT_ROOT / "assets", alias="ASSETS_DIR")
    logs_dir: Path = Field(default=PROJECT_ROOT / "logs", alias="LOGS_DIR")
    prompts_dir: Path = Field(default=PROJECT_ROOT / "prompts", alias="PROMPTS_DIR")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "app_name",
        "default_image_provider",
        "default_llm_provider",
        "default_llm_model",
        "default_tts_provider",
        "default_tts_voice",
        "default_video_provider",
        "default_render_provider",
        "database_url",
        "kling_api_base_url",
        "caption_font_name",
    )
    @classmethod
    def validate_non_blank_strings(cls, value: str) -> str:
        """Reject blank values for required string settings."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("value must not be blank")
        return normalized_value

    @field_validator("default_image_model", "default_tts_model", "default_video_model", mode="before")
    @classmethod
    def normalize_optional_model_defaults(cls, value: str | None) -> str | None:
        """Normalize blank optional provider-model values to ``None``."""

        if value is None:
            return None

        normalized_value = value.strip()
        if not normalized_value:
            return None
        return normalized_value

    @field_validator("ffmpeg_path", "caption_font_file", mode="before")
    @classmethod
    def normalize_optional_paths(cls, value: Path | str | None) -> Path | None:
        """Normalize blank optional paths to ``None`` and resolve relative paths safely."""

        if value is None:
            return None
        if isinstance(value, str):
            normalized_value = value.strip()
            if not normalized_value:
                return None
            value = normalized_value

        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalize and validate log level values."""

        normalized_value = value.strip().upper()
        if normalized_value not in ALLOWED_LOG_LEVELS:
            raise ValueError(
                "log_level must be one of DEBUG, INFO, WARNING, ERROR, or CRITICAL",
            )
        return normalized_value

    @field_validator(
        "provider_timeout_seconds",
        "openai_image_timeout_seconds",
        "kling_video_timeout_seconds",
        "kling_video_poll_interval_seconds",
    )
    @classmethod
    def validate_positive_timeout_seconds(cls, value: float) -> float:
        """Ensure configured timeout values are positive."""

        if value <= 0:
            raise ValueError("timeout seconds must be greater than zero")
        return value

    @field_validator("provider_max_retries")
    @classmethod
    def validate_provider_max_retries(cls, value: int) -> int:
        """Ensure provider retry counts are not negative."""

        if value < 0:
            raise ValueError("provider_max_retries must be zero or greater")
        return value

    @field_validator("artifact_root", "assets_dir", "logs_dir", "prompts_dir", mode="before")
    @classmethod
    def normalize_project_paths(cls, value: Path | str) -> Path:
        """Resolve relative configuration paths from the project root."""

        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def is_development(self) -> bool:
        """Return whether the active environment is development."""

        return self.app_env == "development"

    @property
    def is_testing(self) -> bool:
        """Return whether the active environment is testing."""

        return self.app_env == "testing"

    @property
    def is_production(self) -> bool:
        """Return whether the active environment is production."""

        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
