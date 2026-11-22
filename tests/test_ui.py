from typing import Any

from sqlwhisper.models import ChartSpec, QueryResult
from sqlwhisper.ui import build_context, build_figure, error_message


def make_result(chart: ChartSpec | None, columns: list[str], rows: list[list[Any]]) -> QueryResult:
    return QueryResult(
        sql="SELECT 1",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        elapsed_ms=1,
        attempts=1,
        chart=chart,
    )


# ---- build_figure -----------------------------------------------------------------------


def test_bar_figure_uses_spec_columns() -> None:
    result = make_result(
        ChartSpec(type="bar", x="region", y="total"),
        ["region", "total"],
        [["North", 10], ["South", 20]],
    )
    fig = build_figure(result)
    assert fig is not None
    trace = fig.data[0]
    assert trace.type == "bar"
    assert list(trace.x) == ["North", "South"]
    assert list(trace.y) == [10, 20]


def test_line_figure_draws_lines() -> None:
    result = make_result(
        ChartSpec(type="line", x="day", y="total"),
        ["day", "total"],
        [["2026-08-11", 5], ["2026-08-12", 7]],
    )
    fig = build_figure(result)
    assert fig is not None
    trace = fig.data[0]
    assert trace.type == "scatter"
    assert trace.mode == "lines"
    assert list(trace.y) == [5, 7]


def test_scatter_figure_draws_markers() -> None:
    result = make_result(
        ChartSpec(type="scatter", x="units", y="total"),
        ["units", "total"],
        [[1, 10.5], [2, 21.0]],
    )
    fig = build_figure(result)
    assert fig is not None
    assert fig.data[0].mode == "markers"


def test_figure_follows_spec_not_column_order() -> None:
    result = make_result(
        ChartSpec(type="bar", x="region", y="total"),
        ["units", "region", "total"],
        [[1, "North", 10], [2, "South", 20]],
    )
    fig = build_figure(result)
    assert fig is not None
    assert list(fig.data[0].x) == ["North", "South"]
    assert list(fig.data[0].y) == [10, 20]


def test_no_chart_spec_returns_none() -> None:
    assert build_figure(make_result(None, ["a"], [[1]])) is None


# ---- build_context ----------------------------------------------------------------------


def turn(n: int, sql: str | None = "SELECT 1") -> dict[str, Any]:
    return {"question": f"q{n}", "sql": sql}


def test_context_keeps_last_three() -> None:
    context = build_context([turn(i) for i in range(1, 6)])
    assert [qa["question"] for qa in context] == ["q3", "q4", "q5"]


def test_context_skips_failed_turns() -> None:
    turns = [turn(1), turn(2, None), turn(3), turn(4, ""), turn(5)]
    assert [qa["question"] for qa in build_context(turns)] == ["q1", "q3", "q5"]


def test_context_is_empty_without_turns() -> None:
    assert build_context([]) == []


def test_context_pairs_carry_only_question_and_sql() -> None:
    extra = {**turn(1), "rows": [[1]], "chart": None}
    assert build_context([extra]) == [{"question": "q1", "sql": "SELECT 1"}]


# ---- error_message ----------------------------------------------------------------------


def err(code: str, message: str = "server said", last_sql: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if last_sql is not None:
        body["last_sql"] = last_sql
    return body


def test_llm_unavailable_points_at_ollama() -> None:
    message, sql = error_message(err("llm_unavailable"))
    assert "Ollama" in message
    assert sql is None


def test_validation_failed_shows_reason_and_last_sql() -> None:
    message, sql = error_message(err("validation_failed", "unknown column x", "SELECT x FROM t"))
    assert "unknown column x" in message
    assert sql == "SELECT x FROM t"


def test_unsafe_sql_says_read_only_and_shows_blocked_sql() -> None:
    message, sql = error_message(err("unsafe_sql", "got DELETE", "DELETE FROM t"))
    assert "SELECT" in message
    assert sql == "DELETE FROM t"


def test_query_timeout_says_too_long() -> None:
    message, sql = error_message(err("query_timeout"))
    assert "too long" in message
    assert sql is None


def test_bad_source_and_bad_request_carry_the_server_message() -> None:
    assert "not a csv" in error_message(err("bad_source", "not a csv"))[0]
    assert "question: too short" in error_message(err("bad_request", "question: too short"))[0]


def test_internal_error_is_generic_and_does_not_echo_the_message() -> None:
    message, sql = error_message(err("internal_error", "secret detail"))
    assert "Unexpected" in message
    assert "secret detail" not in message
    assert sql is None


def test_unknown_or_missing_code_falls_back_to_generic() -> None:
    assert "Unexpected" in error_message(err("brand_new_code"))[0]
    assert "Unexpected" in error_message({})[0]


def test_api_unreachable_names_the_api() -> None:
    message, sql = error_message({"code": "api_unreachable"})
    assert "API" in message
    assert "Unexpected" not in message
    assert sql is None
