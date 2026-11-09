from pathlib import Path

import pytest
from pydantic import ValidationError

from sqlwhisper.settings import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.ollama_model == "qwen2.5:7b-instruct"
    assert s.max_rows == 500
    assert s.max_retries == 2
    assert s.data_dir == Path("data")


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setenv("MAX_ROWS", "10")
    s = Settings(_env_file=None)
    assert s.ollama_model == "qwen3:4b"
    assert s.max_rows == 10


def test_non_numeric_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_ROWS", "abc")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_non_positive_limit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_ROWS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_example_covers_every_setting() -> None:
    text = (Path(__file__).parent.parent / ".env.example").read_text()
    keys = {
        line.split("=")[0]
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert keys == {name.upper() for name in Settings.model_fields}
