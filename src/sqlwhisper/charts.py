import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlwhisper.models import ChartSpec, ResultSet

Kind = Literal["numeric", "date", "category", "empty"]

_ISO_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")


def pick_chart(result: ResultSet) -> ChartSpec | None:
    """Chart type from result shape, fixed rules (see docs/ARCHITECTURE.md section 10)."""
    if len(result.rows) <= 1:
        return None
    kinds = [_kind([row[i] for row in result.rows]) for i in range(len(result.columns))]
    by_kind = {
        k: [c for c, kind in zip(result.columns, kinds, strict=True) if kind == k] for k in kinds
    }
    numeric = by_kind.get("numeric", [])
    if not numeric:
        return None
    if by_kind.get("date"):
        return ChartSpec(type="line", x=by_kind["date"][0], y=numeric[0])
    if by_kind.get("category"):
        return ChartSpec(type="bar", x=by_kind["category"][0], y=numeric[0])
    if len(kinds) == 2:  # both numeric
        return ChartSpec(type="scatter", x=numeric[0], y=numeric[1])
    return None


def _kind(values: list[Any]) -> Kind:
    present = [v for v in values if v is not None]
    if not present:
        return "empty"
    if all(isinstance(v, int | float | Decimal) and not isinstance(v, bool) for v in present):
        return "numeric"
    if all(isinstance(v, date) or (isinstance(v, str) and _ISO_DATE.match(v)) for v in present):
        return "date"
    return "category"
