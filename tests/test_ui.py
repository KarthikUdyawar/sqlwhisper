from typing import Any

from sqlwhisper.models import ChartSpec, QueryResult
from sqlwhisper.ui import build_figure


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
