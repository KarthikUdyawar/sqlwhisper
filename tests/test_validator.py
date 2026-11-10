import pytest

from sqlwhisper.errors import SchemaIssue, SyntaxIssue, UnsafeSQL
from sqlwhisper.models import Column, Schema, Table
from sqlwhisper.sources.base import Dialect
from sqlwhisper.validator import validate


def table(name: str, *cols: str) -> Table:
    return Table(name=name, columns=[Column(name=c, type="TEXT") for c in cols])


SCHEMA = Schema(
    tables=[
        table("products", "product_id", "name", "price"),
        table("sales", "sale_id", "product_id", "quantity", "update_date"),
    ]
)


def ok(sql: str, dialect: Dialect = "sqlite") -> str:
    return validate(sql, SCHEMA, dialect).sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM products",
        "SELECT p.name, SUM(s.quantity) AS total FROM sales s "
        "JOIN products p ON p.product_id = s.product_id GROUP BY p.name ORDER BY total DESC",
        "WITH t AS (SELECT product_id, SUM(quantity) AS q FROM sales GROUP BY 1) "
        "SELECT p.name, t.q FROM t JOIN products p ON p.product_id = t.product_id",
        "SELECT name FROM products UNION SELECT name FROM products ORDER BY name",
        "SELECT name FROM products EXCEPT SELECT name FROM products",
        "(SELECT name FROM products)",
        "SELECT name FROM products WHERE price > (SELECT AVG(price) FROM products)",
        "SELECT * FROM sales",
        "SELECT COUNT(*) FROM sales",
        "SELECT 1",
        "SELECT name FROM products;",
        "SELECT strftime('%Y-%m', update_date) AS m, COUNT(*) FROM sales GROUP BY m",
    ],
)
def test_valid_queries_pass(sql: str) -> None:
    assert validate(sql, SCHEMA, "sqlite").sql


def test_returns_normalised_sql() -> None:
    assert ok("select name   from products;") == "SELECT name FROM products"


def test_identifiers_are_case_insensitive() -> None:
    assert ok("SELECT NAME FROM Products")


def test_keyword_inside_identifier_or_string_is_not_a_write() -> None:
    assert ok("SELECT update_date FROM sales")
    assert ok("SELECT name FROM products WHERE name = 'DROP TABLE x'")


@pytest.mark.parametrize(
    "sql",
    [
        "SELEC",
        "SELECT name FROM",
        "SELECT FROM products",
        "I cannot answer that",
        "SELECT 'abc",
        "",
        ";",
    ],
)
def test_syntax_errors(sql: str) -> None:
    with pytest.raises(SyntaxIssue) as exc:
        validate(sql, SCHEMA, "sqlite")
    assert exc.value.args[0]
    assert "\x1b" not in exc.value.args[0]  # no terminal colour codes in model feedback


def test_unknown_table() -> None:
    with pytest.raises(SchemaIssue, match="Table 'orders' not found") as exc:
        ok("SELECT * FROM orders")
    assert "products(" in str(exc.value)  # tells the model what exists


def test_unknown_table_in_join_and_subquery() -> None:
    with pytest.raises(SchemaIssue, match="'nope'"):
        ok("SELECT name FROM products WHERE product_id IN (SELECT id FROM nope)")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT revenue FROM sales",
        "SELECT s.revenue FROM sales s",
        "SELECT name FROM sales",  # exists, but on another table
        "SELECT x.name FROM products",
    ],
)
def test_unknown_column(sql: str) -> None:
    with pytest.raises(SchemaIssue):
        ok(sql)


def test_unknown_column_suggests_closest_name_and_lists_columns() -> None:
    with pytest.raises(SchemaIssue) as exc:
        ok("SELECT quantiti FROM sales")
    message = str(exc.value)
    assert "Did you mean 'quantity'?" in message
    assert "sales(sale_id, product_id, quantity, update_date)" in message


def test_schema_prefix_rejected() -> None:
    with pytest.raises(SchemaIssue, match="schema"):
        ok("SELECT name FROM public.products", "postgres")


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO sales (sale_id) VALUES (1)",
        "UPDATE sales SET quantity = 0",
        "DELETE FROM sales",
        "DROP TABLE sales",
        "DROP TABLE nonexistent",
        "ALTER TABLE sales ADD COLUMN x TEXT",
        "TRUNCATE sales",
        "GRANT ALL ON sales TO bob",
        "EXEC xp_cmdshell 'dir'",
        "PRAGMA table_info(sales)",
        "VACUUM",
        "ATTACH DATABASE 'x.db' AS x",
        "/* hi */ DROP TABLE sales",
        "CREATE TABLE x AS SELECT * FROM sales",
        "SELECT 1; DROP TABLE sales",
        "SELECT name FROM products; SELECT name FROM products",
    ],
)
def test_non_select_is_unsafe(sql: str, dialect: Dialect) -> None:
    with pytest.raises(UnsafeSQL):
        validate(sql, SCHEMA, dialect)


@pytest.mark.parametrize(
    "sql",
    [
        "WITH d AS (DELETE FROM sales RETURNING *) SELECT * FROM d",
        "WITH u AS (UPDATE sales SET quantity = 0 RETURNING *) SELECT * FROM u",
        "WITH i AS (INSERT INTO sales (sale_id) VALUES (1) RETURNING *) SELECT * FROM i",
        "SELECT * INTO newtable FROM sales",
        "SELECT * FROM sales FOR UPDATE",
    ],
)
def test_write_hidden_inside_a_select_is_unsafe(sql: str) -> None:
    with pytest.raises(UnsafeSQL):
        ok(sql, "postgres")


def test_unparseable_write_is_still_unsafe_not_retryable() -> None:
    with pytest.raises(UnsafeSQL):
        ok("DROP TABLE")
    with pytest.raises(UnsafeSQL):
        ok("delete from")


def test_unsafe_wins_over_schema_error() -> None:
    with pytest.raises(UnsafeSQL):
        ok("DELETE FROM nonexistent")


def test_dialect_is_respected() -> None:
    assert ok("SELECT `name` FROM products", "sqlite")
    with pytest.raises(SyntaxIssue):
        ok("SELECT `name` FROM products", "postgres")


def test_postgres_syntax_passes_on_postgres() -> None:
    assert ok("SELECT name FROM products WHERE name ILIKE 'a%'", "postgres")
    assert ok("SELECT update_date::date AS d FROM sales", "postgres")
    assert ok("SELECT g FROM generate_series(1, 3) AS g", "postgres")
