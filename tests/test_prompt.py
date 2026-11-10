from pathlib import Path

import pytest

from sqlwhisper.models import QA, Column, Schema, Table
from sqlwhisper.prompt import conversation, correction, extract_sql, system_prompt
from sqlwhisper.sources.csv import CsvSource

SCHEMA = Schema(
    tables=[
        Table(
            name="products",
            columns=[
                Column(name="product_id", type="INTEGER", pk=True),
                Column(name="name", type="TEXT"),
            ],
        ),
        Table(
            name="sales",
            columns=[
                Column(name="sale_id", type="INTEGER", pk=True),
                Column(name="product_id", type="INTEGER", fk="products.product_id"),
            ],
        ),
    ]
)


def test_system_prompt_has_dialect_schema_and_rules() -> None:
    prompt = system_prompt("postgres", SCHEMA)
    assert "PostgreSQL" in prompt
    assert "products(product_id INTEGER PK, name TEXT)" in prompt
    assert "sales(sale_id INTEGER PK, product_id INTEGER -> products.product_id)" in prompt
    assert "SQL only" in prompt
    assert "Never write data" in prompt
    assert "SQLite" not in prompt


def test_sqlite_dialect_named() -> None:
    assert "SQLite" in system_prompt("sqlite", SCHEMA)


def test_prompt_lists_only_the_schema_it_is_given() -> None:
    only_sales = Schema(tables=[SCHEMA.tables[1]])
    prompt = system_prompt("sqlite", only_sales)
    assert "sales(" in prompt
    assert "products(" not in prompt


def test_prompt_never_contains_row_data(tmp_path: Path) -> None:
    src = CsvSource.from_upload(
        b"name,secret\nalice,TOP_SECRET_VALUE_123\n",
        "people.csv",
        data_dir=tmp_path,
        max_bytes=10**6,
    )
    prompt = system_prompt(src.dialect, src.schema())
    assert "people(" in prompt
    assert "TOP_SECRET_VALUE_123" not in prompt
    assert "alice" not in prompt


def test_conversation_without_context_is_just_the_question() -> None:
    assert conversation("total by region", []) == [{"role": "user", "content": "total by region"}]


def test_conversation_keeps_only_last_three_pairs_in_order() -> None:
    context = [QA(question=f"q{i}", sql=f"SELECT {i}") for i in range(5)]
    messages = conversation("now North", context)
    assert [m["content"] for m in messages] == [
        "q2", "SELECT 2", "q3", "SELECT 3", "q4", "SELECT 4", "now North",
    ]  # fmt: skip
    assert [m["role"] for m in messages] == ["user", "assistant"] * 3 + ["user"]


def test_correction_carries_the_error() -> None:
    message = correction("Column 'x' not found. Did you mean 'y'?")
    assert message["role"] == "user"
    assert "Column 'x' not found. Did you mean 'y'?" in message["content"]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("SELECT a FROM t", "SELECT a FROM t"),
        ("  SELECT a FROM t;  \n", "SELECT a FROM t;"),
        ("```sql\nSELECT a FROM t\n```", "SELECT a FROM t"),
        ("```\nSELECT a FROM t\n```", "SELECT a FROM t"),
        ("```SQL\nSELECT a\nFROM t\n```", "SELECT a\nFROM t"),
        ("Here is the query:\n```sql\nSELECT a FROM t\n```\nHope that helps!", "SELECT a FROM t"),
        ("Sure! Here you go:\nSELECT a FROM t;", "SELECT a FROM t;"),
        ("SELECT a FROM t;\n\nThis query returns a.", "SELECT a FROM t;"),
        ("<think>I should use SELECT b</think>\nSELECT a FROM t", "SELECT a FROM t"),
        ("<think>\nmulti\nline\n</think>\n```sql\nSELECT a FROM t\n```", "SELECT a FROM t"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "WITH x AS (SELECT 1) SELECT * FROM x"),
        ("```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```", "SELECT 1"),
        ("", ""),
        ("I cannot answer that.", "I cannot answer that."),
    ],
)
def test_extract_sql(reply: str, expected: str) -> None:
    assert extract_sql(reply) == expected
