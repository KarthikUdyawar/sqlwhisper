from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine

from sqlwhisper.errors import (
    LLMUnavailable,
    QueryTimeout,
    UnsafeSQL,
    ValidationFailed,
)
from sqlwhisper.models import QA, Message, Schema
from sqlwhisper.pipeline import PipelineConfig, answer
from sqlwhisper.schema import introspect
from sqlwhisper.sources.csv import CsvSource

CSV = b"region,total\nNorth,10\nSouth,20\nNorth,5\nSouth,15\n"
CFG = PipelineConfig(max_rows=100, max_retries=2, timeout_s=5)


class FakeLLM:
    """Returns scripted replies in order (the last one repeats) and records every call."""

    def __init__(self, *replies: str | Exception) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, list[Message]]] = []

    def complete(self, system: str, messages: list[Message]) -> str:
        self.calls.append((system, list(messages)))
        reply = self._replies[min(len(self.calls), len(self._replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def source(tmp_path: Path) -> CsvSource:
    return CsvSource.from_upload(CSV, "sales.csv", data_dir=tmp_path, max_bytes=10**6)


GOOD = "SELECT region, SUM(total) AS total FROM sales GROUP BY region ORDER BY region"


def test_valid_on_first_try(source: CsvSource) -> None:
    llm = FakeLLM(GOOD)
    out = answer("total by region", [], source, llm, CFG)
    assert out.attempts == 1
    assert out.result.rows == [["North", 15], ["South", 35]]
    assert len(llm.calls) == 1


def test_fenced_reply_is_cleaned(source: CsvSource) -> None:
    out = answer("total by region", [], source, FakeLLM(f"```sql\n{GOOD}\n```"), CFG)
    assert out.attempts == 1


def test_hallucinated_column_is_fixed_on_retry(source: CsvSource) -> None:
    llm = FakeLLM("SELECT regio, SUM(total) FROM sales GROUP BY regio", GOOD)
    out = answer("total by region", [], source, llm, CFG)

    assert out.attempts == 2
    assert out.result.rows == [["North", 15], ["South", 35]]
    retry_messages = llm.calls[1][1]
    assert retry_messages[-2] == {
        "role": "assistant",
        "content": "SELECT regio, SUM(total) FROM sales GROUP BY regio",
    }
    assert retry_messages[-1]["role"] == "user"
    assert "regio" in retry_messages[-1]["content"]
    assert "Did you mean 'region'?" in retry_messages[-1]["content"]


def test_runtime_db_error_is_retried_too(source: CsvSource) -> None:
    llm = FakeLLM("SELECT json_extract('{bad', '$.a')", GOOD)
    out = answer("total by region", [], source, llm, CFG)
    assert out.attempts == 2
    assert "did not work" in llm.calls[1][1][-1]["content"]


def test_still_invalid_after_max_retries(source: CsvSource) -> None:
    llm = FakeLLM("SELECT nope FROM sales", "SELECT nada FROM sales", "SELECT zip FROM sales")
    with pytest.raises(ValidationFailed) as exc:
        answer("q", [], source, llm, CFG)
    assert len(llm.calls) == 3  # 1 try + 2 retries
    assert exc.value.last_sql == "SELECT zip FROM sales"
    assert "zip" in str(exc.value)


def test_zero_retries_means_one_attempt(source: CsvSource) -> None:
    llm = FakeLLM("SELECT nope FROM sales")
    cfg = PipelineConfig(max_rows=100, max_retries=0, timeout_s=5)
    with pytest.raises(ValidationFailed):
        answer("q", [], source, llm, cfg)
    assert len(llm.calls) == 1


def test_unsafe_sql_stops_immediately(source: CsvSource) -> None:
    llm = FakeLLM("DROP TABLE sales", GOOD)
    with pytest.raises(UnsafeSQL) as exc:
        answer("q", [], source, llm, CFG)
    assert len(llm.calls) == 1
    assert exc.value.sql == "DROP TABLE sales"


def test_unsafe_sql_after_a_failed_attempt_still_stops(source: CsvSource) -> None:
    llm = FakeLLM("SELECT nope FROM sales", "DELETE FROM sales", GOOD)
    with pytest.raises(UnsafeSQL):
        answer("q", [], source, llm, CFG)
    assert len(llm.calls) == 2


def test_timeout_is_not_retried(source: CsvSource) -> None:
    forever = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    )
    llm = FakeLLM(forever, GOOD)
    cfg = PipelineConfig(max_rows=100, max_retries=2, timeout_s=0.2)
    with pytest.raises(QueryTimeout):
        answer("q", [], source, llm, cfg)
    assert len(llm.calls) == 1


def test_llm_unavailable_propagates(source: CsvSource) -> None:
    with pytest.raises(LLMUnavailable):
        answer("q", [], source, FakeLLM(LLMUnavailable("down")), CFG)


def test_context_is_capped_at_three_pairs(source: CsvSource) -> None:
    context = [QA(question=f"q{i}", sql=f"SELECT {i}") for i in range(5)]
    llm = FakeLLM(GOOD)
    answer("now North", context, source, llm, CFG)
    contents = [m["content"] for m in llm.calls[0][1]]
    assert contents[0] == "q2"
    assert contents[-1] == "now North"
    assert len(contents) == 7


def test_prompt_has_schema_but_no_row_data(source: CsvSource) -> None:
    llm = FakeLLM(GOOD)
    answer("total by region", [], source, llm, CFG)
    system = llm.calls[0][0]
    assert "sales(region TEXT, total BIGINT)" in system
    assert "SQLite" in system
    assert "North" not in system


class SevenTableSource:
    id = "s"
    label = "seven"
    dialect = "sqlite"

    def __init__(self, tmp_path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{tmp_path / 'seven.db'}")
        with self._engine.begin() as conn:
            for name in (
                "orders",
                "customers",
                "products",
                "shipments",
                "invoices",
                "staff",
                "regions",
            ):
                conn.exec_driver_sql(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY, label TEXT)")
        self._schema = introspect(self._engine)

    def engine(self) -> Engine:
        return self._engine

    def schema(self) -> Schema:
        return self._schema


def test_only_selected_tables_reach_the_prompt(tmp_path: Path) -> None:
    llm = FakeLLM("SELECT id FROM orders")
    answer("how many orders per customer", [], SevenTableSource(tmp_path), llm, CFG)  # type: ignore[arg-type]
    system = llm.calls[0][0]
    assert "orders(" in system
    assert "customers(" in system
    assert system.count("(id INTEGER PK, label TEXT)") == 5  # capped at five tables
