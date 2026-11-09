import uuid
from typing import Literal, Self

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from sqlwhisper.errors import SourceError
from sqlwhisper.models import Schema
from sqlwhisper.schema import introspect


def parse_postgres_url(raw: str) -> URL:
    try:
        url = make_url(raw)
    except ArgumentError:
        raise SourceError("invalid database URL") from None
    if url.drivername != "postgresql":
        raise SourceError("only postgresql:// URLs are supported")
    if not url.host or not url.database:
        raise SourceError("URL needs a host and a database name")
    return url


class PostgresSource:
    dialect: Literal["postgres"] = "postgres"

    def __init__(self, url: URL) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.label = f"{url.host}/{url.database}"  # no user, no password
        self._engine = create_engine(
            url.set(drivername="postgresql+psycopg"),
            connect_args={
                "options": "-c default_transaction_read_only=on",
                "connect_timeout": 5,
            },
            pool_pre_ping=True,
        )
        self._schema: Schema | None = None

    @classmethod
    def from_url(cls, raw: str) -> Self:
        """Parse, connect, introspect. Fails fast, never echoes the URL."""
        source = cls(parse_postgres_url(raw))
        try:
            source.schema()
        except SQLAlchemyError:
            source.engine().dispose()
            raise SourceError(f"could not connect to {source.label}") from None
        return source

    def engine(self) -> Engine:
        return self._engine

    def schema(self) -> Schema:
        if self._schema is None:
            self._schema = introspect(self._engine)
        return self._schema
