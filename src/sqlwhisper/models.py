from typing import Any, Literal, TypedDict

from pydantic import BaseModel


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
