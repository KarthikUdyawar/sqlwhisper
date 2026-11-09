from pathlib import Path

from sqlalchemy import create_engine

from sqlwhisper.models import Column, Schema, Table
from sqlwhisper.schema import introspect, select_tables


def build(spec: dict[str, list[str]]) -> Schema:
    return Schema(
        tables=[
            Table(name=t, columns=[Column(name=c, type="TEXT") for c in cols])
            for t, cols in spec.items()
        ]
    )


def names(schema: Schema) -> list[str]:
    return [t.name for t in schema.tables]


def test_introspect_tables_columns_pk_fk(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE products (product_id INTEGER PRIMARY KEY, name TEXT)")
        conn.exec_driver_sql(
            "CREATE TABLE sales (sale_id INTEGER PRIMARY KEY, "
            "product_id INTEGER REFERENCES products(product_id), qty INTEGER)"
        )
    by_name = {t.name: t for t in introspect(engine).tables}

    assert set(by_name) == {"products", "sales"}
    assert [c.name for c in by_name["products"].columns] == ["product_id", "name"]
    sales = {c.name: c for c in by_name["sales"].columns}
    assert sales["sale_id"].pk is True
    assert sales["qty"].pk is False
    assert sales["product_id"].fk == "products.product_id"
    assert sales["qty"].fk is None


def test_small_schema_returned_whole() -> None:
    schema = build({"a": ["x"], "b": ["y"], "c": ["z"]})
    assert names(select_tables("anything at all", schema)) == ["a", "b", "c"]


def test_large_schema_ranked_by_keywords_and_capped() -> None:
    schema = build(
        {
            "orders": ["id", "revenue"],
            "customers": ["id"],
            "products": ["id"],
            "shipments": ["id"],
            "invoices": ["id"],
            "employees": ["id"],
            "regions": ["id"],
            "warehouses": ["id"],
        }
    )
    picked = names(select_tables("total revenue per customer by region", schema))
    assert len(picked) == 5
    assert {"customers", "regions", "orders"} <= set(picked)


def test_plural_and_singular_match() -> None:
    schema = build({f"t{i}": ["id"] for i in range(6)} | {"sales": ["id"]})
    assert names(select_tables("show sale totals", schema, k=1)) == ["sales"]


def test_no_hits_keeps_original_order() -> None:
    schema = build({f"t{i}": ["id"] for i in range(7)})
    assert names(select_tables("hello", schema)) == ["t0", "t1", "t2", "t3", "t4"]
