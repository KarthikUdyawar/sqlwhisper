from pathlib import Path

import pytest
import sqlglot

from sqlwhisper.errors import QueryFailed, QueryTimeout
from sqlwhisper.executor import enforce_limit, run
from sqlwhisper.sources.csv import CsvSource
from sqlwhisper.validator import ValidatedSQL, validate


def make_source(tmp_path: Path, rows: int = 25) -> CsvSource:
    body = "".join(f"{'North' if i % 2 else 'South'},{i}\n" for i in range(rows))
    return CsvSource.from_upload(
        f"region,total\n{body}".encode(), "sales.csv", data_dir=tmp_path, max_bytes=10**7
    )


def prepare(src: CsvSource, sql: str) -> ValidatedSQL:
    return validate(sql, src.schema(), src.dialect)


def limited(sql: str, max_rows: int = 10) -> str:
    tree = sqlglot.parse_one(sql, read="sqlite")
    return enforce_limit(ValidatedSQL(tree, "sqlite"), max_rows).sql


# ---- enforce_limit (pure) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT a FROM t", "SELECT a FROM t LIMIT 11"),
        ("SELECT a FROM t LIMIT 5", "SELECT a FROM t LIMIT 5"),
        ("SELECT a FROM t LIMIT 10", "SELECT a FROM t LIMIT 10"),
        ("SELECT a FROM t LIMIT 11", "SELECT a FROM t LIMIT 11"),
        ("SELECT a FROM t LIMIT 5000", "SELECT a FROM t LIMIT 11"),
        ("SELECT a FROM t LIMIT -1", "SELECT a FROM t LIMIT 11"),
        ("SELECT a FROM t LIMIT 5 OFFSET 20", "SELECT a FROM t LIMIT 5 OFFSET 20"),
        ("SELECT a FROM t LIMIT 5000 OFFSET 20", "SELECT a FROM t LIMIT 11 OFFSET 20"),
        ("SELECT a FROM t ORDER BY a", "SELECT a FROM t ORDER BY a LIMIT 11"),
        ("SELECT a FROM t UNION SELECT a FROM u", "SELECT a FROM t UNION SELECT a FROM u LIMIT 11"),
        ("SELECT a FROM t LIMIT (SELECT 3)", "SELECT a FROM t LIMIT 11"),
    ],
)
def test_enforce_limit(sql: str, expected: str) -> None:
    assert limited(sql) == expected


def test_enforce_limit_does_not_mutate_input() -> None:
    tree = sqlglot.parse_one("SELECT a FROM t", read="sqlite")
    query = ValidatedSQL(tree, "sqlite")
    enforce_limit(query, 10)
    assert query.sql == "SELECT a FROM t"


# ---- run --------------------------------------------------------------------------------


def test_run_returns_columns_and_rows(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=4)
    result = run(
        src,
        prepare(src, "SELECT region, SUM(total) AS t FROM sales GROUP BY region ORDER BY region"),
        max_rows=500,
        timeout_s=5,
    )
    assert result.columns == ["region", "t"]
    assert result.rows == [["North", 4], ["South", 2]]
    assert result.truncated is False
    assert result.elapsed_ms >= 0
    assert result.sql == "SELECT region, SUM(total) AS t FROM sales GROUP BY region ORDER BY region"


def test_run_truncates_and_flags(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=25)
    result = run(src, prepare(src, "SELECT total FROM sales"), max_rows=10, timeout_s=5)
    assert len(result.rows) == 10
    assert result.truncated is True
    assert "LIMIT" not in result.sql  # the +1 detection limit is an implementation detail


def test_run_clamps_a_bigger_user_limit(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=25)
    result = run(src, prepare(src, "SELECT total FROM sales LIMIT 5000"), max_rows=10, timeout_s=5)
    assert len(result.rows) == 10
    assert result.truncated is True


def test_run_keeps_a_smaller_user_limit(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=25)
    result = run(src, prepare(src, "SELECT total FROM sales LIMIT 3"), max_rows=10, timeout_s=5)
    assert len(result.rows) == 3
    assert result.truncated is False


def test_exactly_max_rows_is_not_truncated(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=10)
    result = run(src, prepare(src, "SELECT total FROM sales"), max_rows=10, timeout_s=5)
    assert len(result.rows) == 10
    assert result.truncated is False


def test_colon_and_percent_in_sql_are_literal(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=3)
    sql = "SELECT '12:30' AS t, region LIKE 'No%' AS m, ':x' AS y FROM sales ORDER BY total LIMIT 1"
    result = run(src, prepare(src, sql), max_rows=10, timeout_s=5)
    assert result.rows == [["12:30", 0, ":x"]]


def test_write_fails_on_read_only_engine_even_if_validator_is_bypassed(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=3)
    for stmt in ("INSERT INTO sales VALUES ('X', 1)", "DROP TABLE sales", "DELETE FROM sales"):
        tree = sqlglot.parse_one(stmt, read="sqlite")
        with pytest.raises(QueryFailed, match="readonly"):
            run(src, ValidatedSQL(tree, "sqlite"), max_rows=10, timeout_s=5)
    result = run(src, prepare(src, "SELECT COUNT(*) AS n FROM sales"), max_rows=10, timeout_s=5)
    assert result.rows == [[3]]  # still intact


def test_runtime_db_error_becomes_query_failed(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=3)
    with pytest.raises(QueryFailed):
        run(src, prepare(src, "SELECT json_extract('{bad', '$.a')"), max_rows=10, timeout_s=5)


def test_timeout_raises_and_connection_stays_usable(tmp_path: Path) -> None:
    src = make_source(tmp_path, rows=3)
    forever = prepare(
        src,
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c",
    )
    with pytest.raises(QueryTimeout):
        run(src, forever, max_rows=10, timeout_s=0.3)
    result = run(src, prepare(src, "SELECT COUNT(*) FROM sales"), max_rows=10, timeout_s=5)
    assert result.rows == [[3]]
