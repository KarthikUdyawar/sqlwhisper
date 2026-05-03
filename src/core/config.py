"""SQLWhisper configuration.

Loading strategy (highest priority wins):
  1. Environment variables  (SQLWHISPER_*)
  2. .env.<APP_ENV> file    (e.g. .env.development)
  3. .env file              (base fallback)
  4. config/config.yaml     (non-secret defaults)

Secrets (DB URLs, API keys) → .env only, never config.yaml.
Non-secret tunables (timeouts, limits, model names) → config/config.yaml.

Env var format: SQLWHISPER_<SECTION>__<KEY>
  e.g. SQLWHISPER_OLLAMA__TIMEOUT_SECONDS=60
       SQLWHISPER_DATABASES__DEFAULT__URL=postgresql://...
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.constants import (
    APP_MAX_RETRIES_MAX,
    APP_MAX_RETRIES_MIN,
    APP_MAX_ROWS_MAX,
    APP_MAX_ROWS_MIN,
    APP_MAX_TABLES_MAX,
    APP_MAX_TABLES_MIN,
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
    OLLAMA_TIMEOUT_MAX,
    OLLAMA_TIMEOUT_MIN,
    OLLAMA_TIMEOUT_SECONDS,
    SUPPORTED_DIALECTS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_YAML = _PROJECT_ROOT / CONFIG_DIR / CONFIG_YAML_FILENAME


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open() as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict.

    - dict values merged key-by-key (nested sections not replaced wholesale)
    - all other types: override wins
    """
    result = dict(base)
    for key, override_val in override.items():
        base_val = result.get(key)
        if isinstance(base_val, dict) and isinstance(override_val, dict):
            result[key] = _deep_merge(base_val, override_val)
        else:
            result[key] = override_val
    return result


def _resolve_env_file() -> list[str]:
    """Return env files ordered so the specific file wins (pydantic-settings: later = higher priority)."""
    app_env = os.environ.get("APP_ENV", "development").lower()
    # pydantic-settings v2: last file in list wins → specific env file last
    return [".env", f".env.{app_env}"]


def _assert_no_secrets_in_yaml(
    data: dict[str, Any], source: str = "config.yaml"
) -> None:
    """Raise if yaml data contains database URLs (secrets must come from .env)."""
    databases = data.get("databases", {})
    if not isinstance(databases, dict):
        return
    for alias, db_cfg in databases.items():
        if isinstance(db_cfg, dict) and "url" in db_cfg:
            raise ValueError(
                f"Secret found in {source}: databases.{alias}.url must not be set in "
                "config.yaml. DB URLs contain credentials — put them in .env only."
            )


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class OllamaSettings(BaseSettings):
    """Ollama connection + model settings — all non-secret, safe in config.yaml."""

    model_config = SettingsConfigDict(extra="ignore")

    base_url: str = OLLAMA_BASE_URL
    model: str = DEFAULT_MODEL
    fallback_model: str = FALLBACK_MODEL
    timeout_seconds: int = Field(
        default=OLLAMA_TIMEOUT_SECONDS,
        ge=OLLAMA_TIMEOUT_MIN,
        le=OLLAMA_TIMEOUT_MAX,
    )


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
        """Validate that the database dialect is supported.

        Args:
            v: The dialect string to validate.

        Returns:
            The validated dialect.

        Raises:
            ValueError: If the dialect is not in SUPPORTED_DIALECTS.
        """
        if v not in SUPPORTED_DIALECTS:
            raise ValueError(
                f"Unsupported dialect '{v}'. Choose from: {sorted(SUPPORTED_DIALECTS)}"
            )
        return v


class AppSettings(BaseSettings):
    """Application-level tunables — all non-secret, safe in config.yaml."""

    model_config = SettingsConfigDict(extra="ignore")

    max_rows: int = Field(default=MAX_ROWS, ge=APP_MAX_ROWS_MIN, le=APP_MAX_ROWS_MAX)
    max_retries: int = Field(
        default=MAX_RETRIES, ge=APP_MAX_RETRIES_MIN, le=APP_MAX_RETRIES_MAX
    )
    max_tables_in_prompt: int = Field(
        default=MAX_TABLES_IN_PROMPT,
        ge=APP_MAX_TABLES_MIN,
        le=APP_MAX_TABLES_MAX,
    )


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

    # Lowercased on load so is_production/is_development comparisons are safe
    app_env: str = Field(
        default_factory=lambda: os.environ.get("APP_ENV", "development").lower()
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_yaml_defaults(cls, values: Any) -> Any:
        """Deep-merge config.yaml into defaults before env vars are applied.

        Also guards against secrets (databases.*.url) appearing in yaml.
        """
        if not isinstance(values, dict):
            return values
        yaml_data = _load_yaml(_CONFIG_YAML)
        _assert_no_secrets_in_yaml(yaml_data)
        return _deep_merge(yaml_data, values)

    @classmethod
    def from_yaml(cls, yaml_path: Path | None = None) -> Settings:
        """Instantiate with an explicit yaml path (useful in tests)."""
        yaml_data = _load_yaml(yaml_path or _CONFIG_YAML)
        _assert_no_secrets_in_yaml(yaml_data, source=str(yaml_path or _CONFIG_YAML))
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
        """Return True if the application is running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Return True if the application is running in development environment."""
        return self.app_env == "development"


# Singleton — import and use everywhere.
settings: Settings = Settings()
