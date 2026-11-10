from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field, StringConstraints


class Column(BaseModel):
    name: str
    type: str
    pk: bool = False
    fk: str | None = None  # "table.column"


class Table(BaseModel):
    name: str
    columns: list[Column]


class Schema(BaseModel):
    tables: list[Table]


class ResultSet(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    elapsed_ms: int


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class QA(BaseModel):
    """One earlier turn, sent by the client so follow-ups work ("now only North")."""

    question: str
    sql: str


class Answer(BaseModel):
    result: ResultSet
    attempts: int


class ChartSpec(BaseModel):
    """What to draw. The UI turns this into a Plotly figure."""

    type: Literal["bar", "line", "scatter"]
    x: str
    y: str


class QueryResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    attempts: int
    chart: ChartSpec | None


class SourceInfo(BaseModel):
    source_id: str
    label: str
    tables: list[str]


class UrlRequest(BaseModel):
    url: str


class QueryRequest(BaseModel):
    source_id: str
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    context: list[QA] = Field(default_factory=list, max_length=10)


class Health(BaseModel):
    ollama: bool
    model: bool
    model_name: str


class HistoryEntry(BaseModel):
    id: int
    question: str
    sql: str
    rows: int
    source_label: str
    ts: str
    ok: bool
