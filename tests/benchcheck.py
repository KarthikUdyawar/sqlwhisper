"""Result comparison for the benchmark: values only, never SQL text or column names."""

from collections.abc import Sequence

Row = Sequence[object]


def _norm(value: object) -> object:
    # int and float must compare equal (SUM may return either); 2 places absorb float noise.
    if isinstance(value, int | float) and not isinstance(value, bool):
        return round(float(value), 2)
    return value


def rows_match(actual: Sequence[Row], expected: Sequence[Row], ordered: bool = False) -> bool:
    """True when `actual` holds exactly the expected rows.

    Extra trailing columns are ignored (the model may add a count next to the answer), but a
    missing column fails. Duplicate rows count, so a query that repeats the answer fails.
    """
    if not expected:
        return not actual
    width = len(expected[0])
    if len(actual) != len(expected) or any(len(row) < width for row in actual):
        return False
    got = [tuple(_norm(v) for v in row[:width]) for row in actual]
    want = [tuple(_norm(v) for v in row) for row in expected]
    if not ordered:
        got, want = sorted(got, key=repr), sorted(want, key=repr)
    return got == want
