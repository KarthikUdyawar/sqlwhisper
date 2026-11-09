from typing import Literal, Protocol

from sqlalchemy import Engine

from sqlwhisper.models import Schema

Dialect = Literal["sqlite", "postgres"]


class DataSource(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str:
        """Safe to display and log. Never contains credentials."""
        ...

    @property
    def dialect(self) -> Dialect: ...

    def engine(self) -> Engine:
        """Read-only engine."""
        ...

    def schema(self) -> Schema: ...
