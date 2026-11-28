from benchcheck import rows_match


def test_exact_match() -> None:
    assert rows_match([("North", 120)], [("North", 120)])


def test_extra_trailing_column_passes() -> None:
    assert rows_match([("West", 6)], [("West",)])


def test_missing_column_fails() -> None:
    assert not rows_match([("West",)], [("West", 6)])


def test_swapped_column_order_fails() -> None:
    assert not rows_match([(6, "West")], [("West", 6)])


def test_duplicate_rows_fail() -> None:
    assert not rows_match([("Gadget", 30)] * 12, [("Gadget", 30)])


def test_floats_rounded_to_two_places() -> None:
    assert rows_match([(2.001,)], [(2.0,)])
    assert not rows_match([(2.02,)], [(2.0,)])


def test_int_equals_float() -> None:
    assert rows_match([(1650,)], [(1650.0,)])


def test_none_matches_only_none() -> None:
    assert rows_match([(None,)], [(None,)])
    assert not rows_match([(0,)], [(None,)])


def test_row_order_ignored_unless_ordered() -> None:
    actual = [("North", 2), ("South", 1)]
    expected = [("South", 1), ("North", 2)]
    assert rows_match(actual, expected)
    assert not rows_match(actual, expected, ordered=True)
    assert rows_match(expected, expected, ordered=True)


def test_empty_expected_needs_empty_actual() -> None:
    assert rows_match([], [])
    assert not rows_match([("x",)], [])
