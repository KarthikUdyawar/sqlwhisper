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
