"""Shared pytest fixtures.

Keeps tests hermetic: without this, `Settings()` / `Settings.from_yaml()`
pick up whatever the developer's real `config/config.yaml` and `.env*`
files happen to contain (database URLs, model overrides, ...), so test
outcomes silently depend on the machine they're run on.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

import core.config as config_module
from core.config import Settings


@pytest.fixture(autouse=True)
def isolate_settings_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """Isolate Settings construction from real project config/env files.

    - Redirects `_CONFIG_YAML` to a path that doesn't exist, so
      `_merge_yaml_defaults` sees an empty yaml base instead of the real
      `config/config.yaml`. `Settings.from_yaml(path)` is unaffected — its
      explicit `path` argument is layered on top regardless.
    - Clears `Settings.model_config["env_file"]` so the real `.env` /
      `.env.<APP_ENV>` are never read as a side effect. Tests that need to
      exercise env-file precedence (e.g. via a `Settings` subclass with its
      own `model_config`) already set `env_file` explicitly and are
      unaffected by this.
    - Strips any `SQLWHISPER_*` / `APP_ENV` vars already present in the
      shell, so tests that want specific env vars set exactly what they
      need via `patch.dict(os.environ, {...})`.
    """
    monkeypatch.setattr(config_module, "_CONFIG_YAML", tmp_path / "unused-config.yaml")
    monkeypatch.setitem(Settings.model_config, "env_file", [])

    for key in list(os.environ):
        if key == "APP_ENV" or key.startswith("SQLWHISPER_"):
            monkeypatch.delenv(key, raising=False)

    return
