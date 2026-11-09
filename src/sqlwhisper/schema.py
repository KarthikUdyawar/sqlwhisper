import re

from sqlalchemy import Engine, inspect

from sqlwhisper.models import Column, Schema, Table

_WORD = re.compile(r"[a-z0-9]+")


def introspect(engine: Engine) -> Schema:
    insp = inspect(engine)
    tables: list[Table] = []
    for name in insp.get_table_names():
        pks = set(insp.get_pk_constraint(name)["constrained_columns"])
        fks: dict[str, str] = {}
        for fk in insp.get_foreign_keys(name):
            for col, ref in zip(fk["constrained_columns"], fk["referred_columns"], strict=False):
                fks[col] = f"{fk['referred_table']}.{ref}" if ref else fk["referred_table"]
        columns = [
            Column(
                name=c["name"],
                type=str(c["type"]),
                pk=c["name"] in pks,
                fk=fks.get(c["name"]),
            )
            for c in insp.get_columns(name)
        ]
        tables.append(Table(name=name, columns=columns))
    return Schema(tables=tables)


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower())}


def _score(table: Table, question: set[str]) -> int:
    column_tokens: set[str] = set()
    for column in table.columns:
        column_tokens |= _tokens(column.name)
    return 2 * len(question & _tokens(table.name)) + len(question & column_tokens)


def select_tables(question: str, schema: Schema, k: int = 5) -> Schema:
    """All tables if <= k, else the k best keyword matches (table name hit = 2, column hit = 1)."""
    if len(schema.tables) <= k:
        return schema
    words = _tokens(question)
    ranked = sorted(schema.tables, key=lambda t: -_score(t, words))  # stable: ties keep order
    return Schema(tables=ranked[:k])
