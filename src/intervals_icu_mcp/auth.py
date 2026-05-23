"""Authentication and configuration management for Intervals.icu API."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv, set_key
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DeleteMode = Literal["safe", "full", "none"]
VALID_DELETE_MODES: tuple[DeleteMode, ...] = ("safe", "full", "none")

# Per-request HTTP headers that override env-var credentials, enabling a single
# deploy to serve multiple athletes. Compared case-insensitively.
HEADER_API_KEY = "x-intervals-api-key"
HEADER_ATHLETE_ID = "x-intervals-athlete-id"


class ICUConfig(BaseSettings):
    """Intervals.icu API configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    intervals_icu_api_key: str = ""
    intervals_icu_athlete_id: str = ""
    intervals_icu_delete_mode: DeleteMode = "safe"

    @field_validator("intervals_icu_delete_mode", mode="before")
    @classmethod
    def _normalize_delete_mode(cls, v: object) -> str:
        if v is None or v == "":
            return "safe"
        normalized = str(v).lower().strip()
        if normalized not in VALID_DELETE_MODES:
            raise ValueError(
                "INTERVALS_ICU_DELETE_MODE must be one of: "
                f"{', '.join(VALID_DELETE_MODES)}. Got: '{v}'"
            )
        return normalized


def load_config() -> ICUConfig:
    """Load configuration from .env file.

    Returns:
        ICUConfig instance with configuration from environment variables
    """
    load_dotenv()
    return ICUConfig()


def apply_header_credentials(config: ICUConfig, headers: Mapping[str, str]) -> ICUConfig:
    """Override credentials from per-request HTTP headers, falling back to ``config``.

    Header values take priority over the env-var-derived ``config``. Absent or
    empty-string headers leave the corresponding value untouched. Header-name
    lookup is case-insensitive. ``intervals_icu_delete_mode`` is never affected.

    Args:
        config: Base configuration (typically loaded from env vars).
        headers: Incoming request headers (e.g. from ``get_http_headers()``).

    Returns:
        An ICUConfig with header overrides applied, or ``config`` unchanged when
        no relevant headers are present.
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    updates: dict[str, str] = {}
    api_key = lowered.get(HEADER_API_KEY)
    athlete_id = lowered.get(HEADER_ATHLETE_ID)
    if api_key:
        updates["intervals_icu_api_key"] = api_key
    if athlete_id:
        updates["intervals_icu_athlete_id"] = athlete_id
    return config.model_copy(update=updates) if updates else config


def validate_credentials(config: ICUConfig) -> bool:
    """Check if credentials are properly configured.

    Args:
        config: ICUConfig instance to validate

    Returns:
        True if credentials are valid, False otherwise
    """
    if not config.intervals_icu_api_key or config.intervals_icu_api_key == "your_api_key_here":
        return False
    if not config.intervals_icu_athlete_id or config.intervals_icu_athlete_id == "i123456":
        return False
    return True


def update_env_key(api_key: str, athlete_id: str | None = None) -> None:
    """Update the .env file with new credentials.

    Args:
        api_key: New API key to save
        athlete_id: Optional athlete ID to save
    """
    env_path = Path.cwd() / ".env"

    # Create .env if it doesn't exist
    if not env_path.exists():
        env_path.touch()

    # Update API key
    set_key(str(env_path), "INTERVALS_ICU_API_KEY", api_key)
    os.environ["INTERVALS_ICU_API_KEY"] = api_key

    # Update athlete ID if provided
    if athlete_id:
        set_key(str(env_path), "INTERVALS_ICU_ATHLETE_ID", athlete_id)
        os.environ["INTERVALS_ICU_ATHLETE_ID"] = athlete_id
