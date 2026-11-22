from typing import Any

from sqlwhisper.models import ChartSpec, QueryResult
from sqlwhisper.ui import build_context, build_figure


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
