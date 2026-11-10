import re

from sqlwhisper.models import QA, Column, Message, Schema
from sqlwhisper.sources.base import Dialect

MAX_CONTEXT = 3
_DIALECT_NAMES = {"sqlite": "SQLite", "postgres": "PostgreSQL"}

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```[a-z]*\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_SQL_START = re.compile(r"^\s*(?:select|with)\b", re.IGNORECASE | re.MULTILINE)


def system_prompt(dialect: Dialect, schema: Schema) -> str:
    """Schema and rules only. Row data never goes into a prompt."""
    name = _DIALECT_NAMES[dialect]
    return f"""You are an expert {name} SQL engineer. \
Turn the user's question into one read-only SQL query.

Schema:
{_render_schema(schema)}

Rules:
- Reply with the SQL only. No explanation, no markdown.
- One SELECT statement. Never write data or change the schema.
- Use only the tables and columns listed above, spelled exactly.
- Alias tables when joining and qualify columns with the alias.
- Do not prefix table names with a schema.
- Use {name} syntax and functions only."""


def conversation(question: str, context: list[QA]) -> list[Message]:
    """Last MAX_CONTEXT Q/SQL pairs as chat turns, then the new question."""
    messages: list[Message] = []
    for turn in context[-MAX_CONTEXT:]:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.sql})
    messages.append({"role": "user", "content": question})
    return messages


def correction(error: str) -> Message:
    return {
        "role": "user",
        "content": f"That SQL did not work: {error}\nFix it. Reply with the corrected SQL only.",
    }


def extract_sql(reply: str) -> str:
    """Pull the SQL out of a model reply: drop <think> blocks, fences and surrounding prose."""
    text = _THINK.sub("", reply)
    fenced = _FENCE.search(text)
    if fenced:
        return fenced.group(1).strip()
    start = _SQL_START.search(text)
    if start:
        text = text[start.start() :]
        text = text.split("\n\n", 1)[0]  # trailing explanation after a blank line
    return text.strip()


def _render_schema(schema: Schema) -> str:
    return "\n".join(
        f"{table.name}({', '.join(_render_column(c) for c in table.columns)})"
        for table in schema.tables
    )


def _render_column(column: Column) -> str:
    parts = [column.name, column.type]
    if column.pk:
        parts.append("PK")
    if column.fk:
        parts.append(f"-> {column.fk}")
    return " ".join(parts)
