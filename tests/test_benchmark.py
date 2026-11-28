"""Opt-in accuracy benchmark: 20 questions on a fixed CSV against a real Ollama.

Run with `make bench MODEL=<name>`. Compares result values, never SQL text.
"""

import contextlib
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from benchcheck import rows_match
from sqlwhisper.errors import LLMUnavailable, QueryTimeout, UnsafeSQL, ValidationFailed
from sqlwhisper.llm import OllamaClient
from sqlwhisper.models import QA
from sqlwhisper.pipeline import PipelineConfig, answer
from sqlwhisper.settings import Settings
from sqlwhisper.sources.csv import CsvSource

pytestmark = [pytest.mark.ollama, pytest.mark.bench]

FIXTURES = Path(__file__).parent / "fixtures"
# A cold model load can exceed OLLAMA_TIMEOUT_S on a small GPU; only the warm-up gets this.
WARMUP_TIMEOUT_S = 300.0


@dataclass
class Outcome:
    n: int
    question: str
    ok: bool
    attempts: int  # 0 when the pipeline raised
    seconds: float
    note: str


def _run(
    item: dict[str, Any], source: CsvSource, llm: OllamaClient, cfg: PipelineConfig
) -> Outcome:
    context = [QA(**c) for c in item["context"]]
    start = time.perf_counter()
    try:
        out = answer(item["question"], context, source, llm, cfg)
    except (ValidationFailed, UnsafeSQL, QueryTimeout, LLMUnavailable) as exc:
        seconds = time.perf_counter() - start
        return Outcome(item["id"], item["question"], False, 0, seconds, type(exc).__name__)
    seconds = time.perf_counter() - start
    ok = rows_match(out.result.rows, item["expected"], item["ordered"])
    note = "" if ok else f"got {out.result.rows[:3]}"
    return Outcome(item["id"], item["question"], ok, out.attempts, seconds, note)


def _report(model: str, outcomes: list[Outcome]) -> None:
    print(f"\nBENCH model={model}")
    for o in outcomes:
        status = "ok  " if o.ok else "FAIL"
        tries = o.attempts or "-"
        print(f"Q{o.n:02d} {status} attempts={tries} {o.seconds:5.1f}s  {o.question}  {o.note}")
    total = len(outcomes)
    first = sum(o.ok and o.attempts == 1 for o in outcomes)
    final = sum(o.ok for o in outcomes)
    median = statistics.median(o.seconds for o in outcomes)
    print(
        f"RESULT model={model} first_attempt={first}/{total} final={final}/{total} "
        f"median_s={median:.1f}"
    )


def test_benchmark(request: pytest.FixtureRequest, tmp_path: Path) -> None:
    settings = Settings()
    model: str = request.config.getoption("--bench-model") or settings.ollama_model
    source = CsvSource.from_upload(
        (FIXTURES / "bench.csv").read_bytes(), "bench.csv", data_dir=tmp_path, max_bytes=10**6
    )
    cfg = PipelineConfig(
        max_rows=settings.max_rows,
        max_retries=settings.max_retries,
        timeout_s=settings.query_timeout_s,
    )
    questions = json.loads((FIXTURES / "bench_questions.json").read_text())

    warm = OllamaClient(settings.ollama_url, model, WARMUP_TIMEOUT_S)
    with contextlib.suppress(ValidationFailed, UnsafeSQL):
        answer("How many orders are there?", [], source, warm, cfg)

    llm = OllamaClient(settings.ollama_url, model, settings.ollama_timeout_s)
    outcomes = [_run(item, source, llm, cfg) for item in questions]
    _report(model, outcomes)

    assert any(o.ok for o in outcomes), "0 correct answers: check the fixture and Ollama setup"
