import time
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

from sqlwhisper.errors import QueryFailed, QueryTimeout
from sqlwhisper.models import ResultSet
from sqlwhisper.sources.base import DataSource
from sqlwhisper.validator import ValidatedSQL

_PG_CANCELED = "57014"  # SQLSTATE query_canceled (statement_timeout)


def enforce_limit(query: ValidatedSQL, max_rows: int) -> ValidatedSQL:
    """Cap the query at max_rows + 1 (the extra row detects truncation).

    A literal LIMIT <= max_rows is kept; anything else (none, bigger, ALL, -1, FETCH, subquery)
    is replaced.
    """
    tree = query.tree
    if not isinstance(tree, exp.Query):
        return query
    existing = tree.args.get("limit")
    n = max_rows + 1
    if isinstance(existing, exp.Limit):
        value = existing.expression
        if isinstance(value, exp.Literal) and value.is_int and int(value.name) <= max_rows:
            n = int(value.name)
    return ValidatedSQL(tree.limit(n, copy=True), query.dialect)


def _arm_sqlite(conn: Connection, timeout_s: float) -> Callable[[], None]:
    raw = cast(Any, conn.connection.dbapi_connection)
    deadline = time.monotonic() + timeout_s
    raw.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    return lambda: raw.set_progress_handler(None, 0)


def _arm_postgres(conn: Connection, timeout_s: float) -> Callable[[], None]:
    conn.exec_driver_sql(f"SET LOCAL statement_timeout = {int(timeout_s * 1000)}")
    return lambda: None


_ARM = {"sqlite": _arm_sqlite, "postgres": _arm_postgres}


def _translate(error: SQLAlchemyError) -> Exception:
    orig = getattr(error, "orig", None)
    if getattr(orig, "sqlstate", None) == _PG_CANCELED or str(orig) == "interrupted":
        return QueryTimeout("query exceeded the time limit")
    lines = str(orig or error).strip().splitlines()
    return QueryFailed(lines[0] if lines else "query failed")


def run(source: DataSource, query: ValidatedSQL, *, max_rows: int, timeout_s: float) -> ResultSet:
    limited = enforce_limit(query, max_rows)
    # Escape ':' so text() never reads a colon inside the SQL as a bind parameter.
    statement = text(limited.sql.replace(":", r"\:"))
    started = time.perf_counter()
    try:
        with source.engine().connect() as conn:
            disarm = _ARM[source.dialect](conn, timeout_s)
            try:
                result = conn.execute(statement)
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
            finally:
                disarm()
    except SQLAlchemyError as e:
        raise _translate(e) from None
    truncated = len(rows) > max_rows
    return ResultSet(
        sql=query.sql,  # the model's query, not the +1 implementation limit
        columns=columns,
        rows=rows[:max_rows],
        truncated=truncated,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
