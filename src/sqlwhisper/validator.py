import difflib
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, SqlglotError, TokenError
from sqlglot.optimizer.qualify import qualify

from sqlwhisper.errors import SchemaIssue, SyntaxIssue, UnsafeSQL
from sqlwhisper.models import Schema
from sqlwhisper.sources.base import Dialect

# Nodes that must not appear anywhere in the tree (covers writes hidden in CTEs/subqueries).
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Grant,
    exp.Revoke,
    exp.Into,  # SELECT ... INTO creates a table in Postgres
    exp.Copy,
    exp.Lock,  # FOR UPDATE
    exp.Pragma,
    exp.Set,
)
# First word of a statement that must never be retried, even when it does not parse.
_WRITE_WORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "truncate",
        "grant",
        "revoke",
        "create",
        "merge",
        "exec",
        "execute",
        "call",
        "pragma",
        "attach",
        "detach",
        "copy",
        "vacuum",
        "replace",
        "set",
        "lock",
        "reindex",
    }
)
_FIRST_WORD = re.compile(r"\s*(\w+)")
_NOISE = re.compile(r"\x1b\[[0-9;]*m|\s*Line: \d+, Col: \d+\.?")
_BAD_NAME = re.compile(r"Column '(\w+)'|Unknown column: (\w+)")


@dataclass(frozen=True)
class ValidatedSQL:
    """A parsed single read-only query. Only `validate` should build one."""

    tree: exp.Expr
    dialect: Dialect

    @property
    def sql(self) -> str:
        return self.tree.sql(dialect=self.dialect)


def validate(sql: str, schema: Schema, dialect: Dialect) -> ValidatedSQL:
    """Syntax, then safety, then schema. Raises SyntaxIssue | UnsafeSQL | SchemaIssue."""
    tree = _parse(sql, dialect)
    _check_safe(tree, sql)
    _check_schema(tree, schema, dialect)
    return ValidatedSQL(tree, dialect)


def _clean(error: object) -> str:
    return _NOISE.sub("", str(error)).strip()


def _parse(sql: str, dialect: Dialect) -> exp.Expr:
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except (ParseError, TokenError) as e:
        if _writes(sql):
            raise UnsafeSQL("only SELECT queries are allowed") from None
        raise SyntaxIssue(_clean(e)) from None
    if not statements:
        raise SyntaxIssue("empty query")
    if len(statements) > 1:
        raise UnsafeSQL("only a single statement is allowed")
    return statements[0]


def _writes(sql: str) -> bool:
    first = _FIRST_WORD.match(sql)
    return first is not None and first.group(1).lower() in _WRITE_WORDS


def _check_safe(tree: exp.Expr, sql: str) -> None:
    if not isinstance(tree, exp.Query):
        if isinstance(tree, _FORBIDDEN) or _writes(sql):
            raise UnsafeSQL(f"only SELECT queries are allowed, got {type(tree).__name__.upper()}")
        raise SyntaxIssue("expected a single SELECT statement")
    bad = tree.find(*_FORBIDDEN)
    if bad is not None:
        raise UnsafeSQL(f"{type(bad).__name__.upper()} is not allowed")
    if isinstance(tree, exp.Select) and not tree.expressions:
        raise SyntaxIssue("no columns selected")  # sqlglot accepts `SELECT FROM t`


def _check_schema(tree: exp.Expr, schema: Schema, dialect: Dialect) -> None:
    known = {t.name.lower() for t in schema.tables}
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:  # table-valued function such as generate_series()
            continue
        if table.db:
            raise SchemaIssue(f"Do not prefix tables with a schema; use '{table.name}' alone.")
        if name not in known and name not in ctes:
            raise SchemaIssue(f"Table '{table.name}' not found. {_catalog(schema, None)}")
        used.add(name)

    mapping: dict[str, object] = {
        t.name: {c.name: c.type for c in t.columns} for t in schema.tables
    }
    try:
        qualify(
            tree.copy(), schema=mapping, dialect=dialect, quote_identifiers=False, identify=False
        )
    except OptimizeError as e:
        raise SchemaIssue(_column_message(_clean(e), schema, used)) from None
    except SqlglotError:
        # ponytail: qualify cannot analyse this construct; the DB rejects real errors, and the
        # read-only layers do not depend on this check. Revisit if it shows up in benchmarks.
        pass


def _catalog(schema: Schema, only: set[str] | None) -> str:
    tables = [t for t in schema.tables if only is None or t.name.lower() in only]
    return "Available: " + "; ".join(
        f"{t.name}({', '.join(c.name for c in t.columns)})" for t in tables
    )


def _column_message(message: str, schema: Schema, used: set[str]) -> str:
    found = _BAD_NAME.search(message)
    if found:
        name = found.group(1) or found.group(2)
        close = difflib.get_close_matches(
            name, [c.name for t in schema.tables for c in t.columns], n=1
        )
        if close:
            message += f" Did you mean '{close[0]}'?"
    return f"{message} {_catalog(schema, used or None)}"
