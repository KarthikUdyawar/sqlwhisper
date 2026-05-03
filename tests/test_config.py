"""Tests for src/core/config.py."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from core.config import (
    AppSettings,
    DatabaseSettings,
    OllamaSettings,
    Settings,
    _load_yaml,
    _resolve_env_file,
)
from core.constants import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    MAX_RETRIES,
    MAX_ROWS,
    MAX_TABLES_IN_PROMPT,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT_SECONDS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# _load_yaml
# ---------------------------------------------------------------------------


class TestLoadYaml:
    def test_returns_dict_for_valid_file(self, tmp_path: Path) -> None:
        p = _yaml(tmp_path, "ollama:\n  model: test:7b\n")
        result = _load_yaml(p)
        assert result == {"ollama": {"model": "test:7b"}}

    def test_returns_empty_dict_for_missing_file(self, tmp_path: Path) -> None:
        result = _load_yaml(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_returns_empty_dict_for_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("")
        assert _load_yaml(p) == {}


# ---------------------------------------------------------------------------
# _resolve_env_file
# ---------------------------------------------------------------------------


class TestResolveEnvFile:
    def test_defaults_to_development(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "APP_ENV"}
        with patch.dict(os.environ, env, clear=True):
            files = _resolve_env_file()
        assert files[0] == ".env.development"
        assert files[1] == ".env"

    def test_uses_app_env(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            files = _resolve_env_file()
        assert files[0] == ".env.production"

    def test_lowercases_app_env(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "STAGING"}):
            files = _resolve_env_file()
        assert files[0] == ".env.staging"

    def test_always_includes_base_env_as_fallback(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "staging"}):
            files = _resolve_env_file()
        assert ".env" in files


# ---------------------------------------------------------------------------
# OllamaSettings
# ---------------------------------------------------------------------------


class TestOllamaSettings:
    def test_defaults_match_constants(self) -> None:
        cfg = OllamaSettings()
        assert cfg.base_url == OLLAMA_BASE_URL
        assert cfg.model == DEFAULT_MODEL
        assert cfg.fallback_model == FALLBACK_MODEL
        assert cfg.timeout_seconds == OLLAMA_TIMEOUT_SECONDS

    def test_custom_values(self) -> None:
        cfg = OllamaSettings(base_url="http://remote:11434", timeout_seconds=60)
        assert cfg.base_url == "http://remote:11434"
        assert cfg.timeout_seconds == 60

    def test_timeout_too_low_raises(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            OllamaSettings(timeout_seconds=0)

    def test_timeout_too_high_raises(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 300"):
            OllamaSettings(timeout_seconds=301)

    def test_timeout_boundary_values_accepted(self) -> None:
        assert OllamaSettings(timeout_seconds=1).timeout_seconds == 1
        assert OllamaSettings(timeout_seconds=300).timeout_seconds == 300


# ---------------------------------------------------------------------------
# DatabaseSettings
# ---------------------------------------------------------------------------


class TestDatabaseSettings:
    def test_valid_sqlite(self) -> None:
        db = DatabaseSettings(url="sqlite:///./dev.db", dialect="sqlite")
        assert db.dialect == "sqlite"

    def test_url_is_secretstr(self) -> None:
        db = DatabaseSettings(
            url="postgresql://user:s3cr3t@host/db", dialect="postgresql"
        )
        assert "s3cr3t" not in repr(db)
        assert "s3cr3t" not in str(db)
        assert "s3cr3t" in db.url.get_secret_value()

    def test_unsupported_dialect_raises(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported dialect"):
            DatabaseSettings(url="x://x/x", dialect="oracle")

    def test_unsupported_dialect_error_names_valid_options(self) -> None:
        with pytest.raises(ValidationError, match="postgresql"):
            DatabaseSettings(url="x://x/x", dialect="oracle")

    @pytest.mark.parametrize("dialect", ["postgresql", "sqlite", "mysql"])
    def test_all_supported_dialects_accepted(self, dialect: str) -> None:
        db = DatabaseSettings(url="x://x/x", dialect=dialect)
        assert db.dialect == dialect


# ---------------------------------------------------------------------------
# AppSettings
# ---------------------------------------------------------------------------


class TestAppSettings:
    def test_defaults_match_constants(self) -> None:
        cfg = AppSettings()
        assert cfg.max_rows == MAX_ROWS
        assert cfg.max_retries == MAX_RETRIES
        assert cfg.max_tables_in_prompt == MAX_TABLES_IN_PROMPT

    def test_max_rows_too_low_raises(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            AppSettings(max_rows=0)

    def test_max_rows_too_high_raises(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 10000"):
            AppSettings(max_rows=10_001)

    def test_max_rows_boundary_values_accepted(self) -> None:
        assert AppSettings(max_rows=1).max_rows == 1
        assert AppSettings(max_rows=10_000).max_rows == 10_000

    def test_max_retries_too_low_raises(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            AppSettings(max_retries=0)

    def test_max_retries_too_high_raises(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 10"):
            AppSettings(max_retries=11)

    def test_max_tables_in_prompt_boundary(self) -> None:
        assert AppSettings(max_tables_in_prompt=1).max_tables_in_prompt == 1
        assert AppSettings(max_tables_in_prompt=20).max_tables_in_prompt == 20


# ---------------------------------------------------------------------------
# Settings (root)
# ---------------------------------------------------------------------------


class TestSettings:
    def test_from_yaml_loads_ollama_block(self, tmp_path: Path) -> None:
        p = _yaml(
            tmp_path,
            """
ollama:
  base_url: http://test:11434
  model: test-model:7b
  timeout_seconds: 15
app:
  max_rows: 100
""",
        )
        s = Settings.from_yaml(p)
        assert s.ollama.base_url == "http://test:11434"
        assert s.ollama.model == "test-model:7b"
        assert s.ollama.timeout_seconds == 15
        assert s.app.max_rows == 100

    def test_from_yaml_missing_file_uses_constants_defaults(
        self, tmp_path: Path
    ) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        assert s.ollama.model == DEFAULT_MODEL
        assert s.app.max_rows == MAX_ROWS
        assert s.app.max_retries == MAX_RETRIES

    def test_databases_empty_by_default(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        assert s.databases == {}

    def test_db_accessor_returns_correct_entry(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        s.databases["local"] = DatabaseSettings(
            url="sqlite:///./x.db", dialect="sqlite"
        )
        db = s.db("local")
        assert db.dialect == "sqlite"
        assert "x.db" in db.url.get_secret_value()

    def test_db_accessor_missing_alias_raises_key_error(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        with pytest.raises(KeyError, match="not found"):
            s.db("nonexistent")

    def test_db_accessor_error_lists_available_aliases(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        s.databases["prod"] = DatabaseSettings(
            url="postgresql://x/y", dialect="postgresql"
        )
        with pytest.raises(KeyError, match="prod"):
            s.db("missing")

    def test_db_accessor_default_alias(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        s.databases["default"] = DatabaseSettings(
            url="sqlite:///./d.db", dialect="sqlite"
        )
        assert s.db().dialect == "sqlite"

    def test_is_production_true(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        object.__setattr__(s, "app_env", "production")
        assert s.is_production is True
        assert s.is_development is False

    def test_is_development_true(self, tmp_path: Path) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        object.__setattr__(s, "app_env", "development")
        assert s.is_development is True
        assert s.is_production is False

    def test_neither_production_nor_development_for_staging(
        self, tmp_path: Path
    ) -> None:
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        object.__setattr__(s, "app_env", "staging")
        assert s.is_production is False
        assert s.is_development is False

    def test_env_var_overrides_yaml_defaults(self, tmp_path: Path) -> None:
        # Settings() (no args) reads env vars; env vars beat yaml defaults.
        with patch.dict(os.environ, {"SQLWHISPER_OLLAMA__TIMEOUT_SECONDS": "99"}):
            s = Settings()
        assert s.ollama.timeout_seconds == 99
