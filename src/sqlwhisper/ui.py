from typing import Any

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from sqlwhisper.models import QueryResult

_CONTEXT_TURNS = 3  # same cap as the server (D-16)
_DRAW = {"bar": px.bar, "line": px.line, "scatter": px.scatter}


def build_figure(result: QueryResult) -> Figure | None:
    """Chart spec to Plotly figure. The API sends the spec, the UI owns Plotly (D-10)."""
    spec = result.chart
    if spec is None:
        return None
    frame = pd.DataFrame(result.rows, columns=result.columns)
    return _DRAW[spec.type](frame, x=spec.x, y=spec.y)


def build_context(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Last 3 answered turns as Q/SQL pairs. A turn without SQL (it failed) is no context."""
    answered = [t for t in turns if t.get("sql")]
    return [{"question": t["question"], "sql": t["sql"]} for t in answered[-_CONTEXT_TURNS:]]
