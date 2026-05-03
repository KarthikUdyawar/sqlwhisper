"""SQLWhisper configuration.

Loading strategy (highest priority wins):
  1. Environment variables  (SQLWHISPER__*)
  2. .env.<APP_ENV> file    (e.g. .env.development)
  3. .env file              (base fallback)
  4. config/config.yaml     (non-secret defaults)

Secrets (DB URLs, API keys) → .env only, never config.yaml.
Non-secret tunables (timeouts, limits, model names) → config/config.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.constants import (
    CONFIG_DIR,
    CONFIG_YAML_FILENAME,
    DEFAULT_MODEL,
    ENV_NESTED_DELIMITER,
    ENV_PREFIX,
    FALLBACK_MODEL,
    MAX_RETRIES,
    MAX_ROWS,
    MAX_TABLES_IN_PROMPT,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT_SECONDS,
    SUPPORTED_DIALECTS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # …/sqlwhisper/
_CONFIG_YAML = _PROJECT_ROOT / CONFIG_DIR / CONFIG_YAML_FILENAME


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open() as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _resolve_env_file() -> list[str]:
    """Return env files to load, most-specific first."""
    app_env = os.environ.get("APP_ENV", "development").lower()
    return [f".env.{app_env}", ".env"]


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class OllamaSettings(BaseSettings):
    """Ollama connection + model settings — all non-secret, safe in config.yaml."""

    model_config = SettingsConfigDict(extra="ignore")

    base_url: str = OLLAMA_BASE_URL
    model: str = DEFAULT_MODEL
    fallback_model: str = FALLBACK_MODEL
    timeout_seconds: int = Field(default=OLLAMA_TIMEOUT_SECONDS, ge=1, le=300)


class DatabaseSettings(BaseSettings):
    """Per-database config.

    url is a secret (contains credentials) → must come from .env, not config.yaml.
    dialect is non-secret → may come from either.
    """

    model_config = SettingsConfigDict(extra="ignore")

    url: SecretStr  # never logged or serialised as plain text
    dialect: str

    @field_validator("dialect")
    @classmethod
    def dialect_must_be_supported(cls, v: str) -> str:
        if v not in SUPPORTED_DIALECTS:
            raise ValueError(
                f"Unsupported dialect '{v}'. Choose from: {sorted(SUPPORTED_DIALECTS)}"
            )
        return v


class AppSettings(BaseSettings):
    """Application-level tunables — all non-secret, safe in config.yaml."""

    model_config = SettingsConfigDict(extra="ignore")

    max_rows: int = Field(default=MAX_ROWS, ge=1, le=10_000)
    max_retries: int = Field(default=MAX_RETRIES, ge=1, le=10)
    max_tables_in_prompt: int = Field(default=MAX_TABLES_IN_PROMPT, ge=1, le=20)


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Root settings object.

    Loads config/config.yaml for defaults, then layers .env / env vars on top.
    DB URLs are SecretStr — they never appear in logs or repr().
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    databases: dict[str, DatabaseSettings] = Field(default_factory=dict)
    app: AppSettings = Field(default_factory=AppSettings)

    # APP_ENV is read-only meta; not nested under a prefix
    app_env: str = Field(
        default_factory=lambda: os.environ.get("APP_ENV", "development")
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_yaml_defaults(cls, values: Any) -> Any:
        """Merge config.yaml into defaults before env vars are applied."""
        yaml_data = _load_yaml(_CONFIG_YAML)
        if not isinstance(values, dict):
            return values
        # yaml_data is the base; explicit values (env/init) win
        merged: dict[str, Any] = {**yaml_data, **values}
        return merged

    @classmethod
    def from_yaml(cls, yaml_path: Path | None = None) -> Settings:
        """Instantiate with an explicit yaml path (useful in tests)."""
        yaml_data = _load_yaml(yaml_path or _CONFIG_YAML)
        return cls(**yaml_data)

    def db(self, alias: str = "default") -> DatabaseSettings:
        """Convenience accessor — raises KeyError with a helpful message."""
        try:
            return self.databases[alias]
        except KeyError:
            available = list(self.databases.keys())
            raise KeyError(
                f"Database alias '{alias}' not found. "
                f"Available: {available}. "
                "Check config/config.yaml and .env."
            ) from None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


# Singleton — import and use everywhere.
settings: Settings = Settings()
