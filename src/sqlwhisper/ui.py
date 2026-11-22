from typing import Any

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from sqlwhisper.models import QueryResult

_CONTEXT_TURNS = 3  # same cap as the server (D-16)
_DRAW = {"bar": px.bar, "line": px.line, "scatter": px.scatter}
_ERROR_TEXT = {
    "llm_unavailable": "Ollama is not reachable. Check that it is running and the model is pulled.",
    "unsafe_sql": "Blocked: only read-only SELECT queries are allowed.",
    "query_timeout": "The query ran too long and was stopped. Try a narrower question.",
    "validation_failed": "Could not produce valid SQL: {message}",
    "bad_source": "Problem with the data source: {message}",
    "bad_request": "Invalid request: {message}",
}
_GENERIC_ERROR = "Unexpected error. Check the API log."
_SHOWS_SQL = {"validation_failed", "unsafe_sql"}  # the user can learn from the rejected SQL


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


def error_message(body: dict[str, Any]) -> tuple[str, str | None]:
    """API error body to (user text, SQL worth showing). Unknown codes stay generic."""
    code = body.get("code", "")
    template = _ERROR_TEXT.get(code, _GENERIC_ERROR)
    sql = body.get("last_sql") if code in _SHOWS_SQL else None
    return template.format(message=body.get("message", "")), sql
