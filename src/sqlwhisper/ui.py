import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from sqlwhisper.models import QueryResult

_DRAW = {"bar": px.bar, "line": px.line, "scatter": px.scatter}


def build_figure(result: QueryResult) -> Figure | None:
    """Chart spec to Plotly figure. The API sends the spec, the UI owns Plotly (D-10)."""
    spec = result.chart
    if spec is None:
        return None
    frame = pd.DataFrame(result.rows, columns=result.columns)
    return _DRAW[spec.type](frame, x=spec.x, y=spec.y)
