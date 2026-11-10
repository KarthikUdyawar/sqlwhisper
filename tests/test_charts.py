from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from sqlwhisper.charts import pick_chart
from sqlwhisper.models import ChartSpec, ResultSet


def result(columns: list[str], rows: list[list[Any]]) -> ResultSet:
    return ResultSet(sql="", columns=columns, rows=rows, truncated=False, elapsed_ms=0)


def test_single_row_is_none() -> None:
    assert pick_chart(result(["region", "total"], [["North", 10]])) is None


def test_no_rows_is_none() -> None:
    assert pick_chart(result(["region", "total"], [])) is None


def test_no_numeric_column_is_none() -> None:
    assert pick_chart(result(["region", "name"], [["N", "a"], ["S", "b"]])) is None


def test_date_plus_numeric_is_line() -> None:
    rows = [["2024-01-01", 5], ["2024-01-02", 7]]
    assert pick_chart(result(["day", "total"], rows)) == ChartSpec(type="line", x="day", y="total")


@pytest.mark.parametrize(
    "stamp",
    [
        ("2024-01", "2024-02"),
        ("2024-01-31", "2024-02-01"),
        ("2024-01-31 10:30:00", "2024-02-01 11:00:00"),
        ("2024-01-31T10:30:00.123", "2024-02-01T11:00:00"),
        (date(2024, 1, 31), date(2024, 2, 1)),
        (datetime(2024, 1, 31, 10), datetime(2024, 2, 1, 11)),
    ],
)
def test_date_like_values(stamp: tuple[Any, Any]) -> None:
    rows = [[stamp[0], 1], [stamp[1], 2]]
    assert pick_chart(result(["month", "n"], rows)) == ChartSpec(type="line", x="month", y="n")


def test_categorical_plus_numeric_is_bar() -> None:
    rows = [["North", 15], ["South", 35]]
    assert pick_chart(result(["region", "total"], rows)) == ChartSpec(
        type="bar", x="region", y="total"
    )


def test_numeric_column_may_come_first() -> None:
    rows = [[15, "North"], [35, "South"]]
    assert pick_chart(result(["total", "region"], rows)) == ChartSpec(
        type="bar", x="region", y="total"
    )


def test_two_numeric_columns_is_scatter() -> None:
    rows = [[1, 2.5], [2, 3.5], [3, 9.0]]
    assert pick_chart(result(["price", "qty"], rows)) == ChartSpec(
        type="scatter", x="price", y="qty"
    )


def test_three_numeric_columns_is_none() -> None:
    assert pick_chart(result(["a", "b", "c"], [[1, 2, 3], [4, 5, 6]])) is None


def test_date_wins_over_category() -> None:
    rows = [["2024-01", "North", 1], ["2024-02", "South", 2]]
    spec = pick_chart(result(["month", "region", "n"], rows))
    assert spec == ChartSpec(type="line", x="month", y="n")


def test_nulls_are_ignored_when_classifying() -> None:
    rows: list[list[Any]] = [["North", None], ["South", 35], [None, 10]]
    assert pick_chart(result(["region", "total"], rows)) == ChartSpec(
        type="bar", x="region", y="total"
    )


def test_all_null_column_is_not_numeric() -> None:
    assert pick_chart(result(["region", "total"], [["N", None], ["S", None]])) is None


def test_bool_is_not_numeric() -> None:
    assert pick_chart(result(["region", "flag"], [["N", True], ["S", False]])) is None


def test_decimal_counts_as_numeric() -> None:
    rows = [["N", Decimal("1.5")], ["S", Decimal("2")]]
    assert pick_chart(result(["region", "total"], rows)) is not None


def test_mixed_strings_and_numbers_is_category() -> None:
    assert pick_chart(result(["v", "n"], [["a", 1], [2, 2]])) == ChartSpec(type="bar", x="v", y="n")


def test_year_only_strings_are_categories() -> None:
    rows = [["2023", 5], ["2024", 7]]
    assert pick_chart(result(["year", "n"], rows)) == ChartSpec(type="bar", x="year", y="n")
