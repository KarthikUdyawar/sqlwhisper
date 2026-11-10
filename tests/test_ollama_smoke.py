"""Opt-in: needs a running Ollama with the configured model. Run with `make smoke`."""

from pathlib import Path

import pytest

from sqlwhisper.llm import OllamaClient
from sqlwhisper.pipeline import PipelineConfig, answer
from sqlwhisper.settings import Settings
from sqlwhisper.sources.csv import CsvSource

pytestmark = pytest.mark.ollama


def test_real_model_answers_a_simple_question(tmp_path: Path) -> None:
    settings = Settings()
    source = CsvSource.from_upload(
        b"region,total\nNorth,10\nSouth,20\nNorth,5\nSouth,15\n",
        "sales.csv",
        data_dir=tmp_path,
        max_bytes=10**6,
    )
    llm = OllamaClient(settings.ollama_url, settings.ollama_model, settings.ollama_timeout_s)
    cfg = PipelineConfig(
        max_rows=settings.max_rows,
        max_retries=settings.max_retries,
        timeout_s=settings.query_timeout_s,
    )

    out = answer("What is the total by region?", [], source, llm, cfg)

    rows = sorted(tuple(sorted(str(v) for v in row)) for row in out.result.rows)
    assert rows == [("15", "North"), ("35", "South")]
