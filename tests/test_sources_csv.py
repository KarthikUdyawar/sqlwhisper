from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from sqlwhisper.errors import SourceError
from sqlwhisper.sources.csv import CsvSource, purge_uploads

LIMIT = 1024 * 1024


def load(tmp_path: Path, content: str, name: str = "sales.csv", limit: int = LIMIT) -> CsvSource:
    return CsvSource.from_upload(content.encode(), name, data_dir=tmp_path, max_bytes=limit)


def columns(src: CsvSource) -> list[str]:
    return [c.name for c in src.schema().tables[0].columns]


def test_table_named_from_filename(tmp_path: Path) -> None:
    src = load(tmp_path, "a,b\n1,2\n", name="Q3 Sales.csv")
    assert [t.name for t in src.schema().tables] == ["q3_sales"]
    assert src.label == "Q3 Sales.csv"
    assert src.dialect == "sqlite"


def test_headers_normalised(tmp_path: Path) -> None:
    src = load(tmp_path, "Order Date,Unit Price\n2024-01-01,3.5\n")
    assert columns(src) == ["order_date", "unit_price"]


def test_duplicate_headers_deduped(tmp_path: Path) -> None:
    assert columns(load(tmp_path, "a,A,a\n1,2,3\n")) == ["a", "a_2", "a_3"]


def test_header_starting_with_digit_prefixed(tmp_path: Path) -> None:
    assert columns(load(tmp_path, "1st,2nd\n1,2\n")) == ["col_1st", "col_2nd"]


def test_data_is_queryable(tmp_path: Path) -> None:
    src = load(tmp_path, "region,total\nNorth,10\nSouth,20\n")
    with src.engine().connect() as conn:
        assert conn.execute(text("SELECT SUM(total) FROM sales")).scalar_one() == 30


@pytest.mark.parametrize("stmt", ["INSERT INTO sales VALUES ('X', 1)", "DROP TABLE sales"])
def test_engine_is_read_only(tmp_path: Path, stmt: str) -> None:
    src = load(tmp_path, "region,total\nNorth,10\n")
    with pytest.raises(OperationalError), src.engine().begin() as conn:
        conn.execute(text(stmt))


def test_rejects_non_csv(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="csv"):
        load(tmp_path, "a,b\n1,2\n", name="data.txt")


def test_rejects_empty_file(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="empty"):
        load(tmp_path, "")


def test_rejects_header_only(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="no data rows"):
        load(tmp_path, "a,b\n")


def test_rejects_oversize(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="too large"):
        load(tmp_path, "a,b\n1,2\n" * 10, limit=10)


def test_rejects_undecodable_bytes(tmp_path: Path) -> None:
    with pytest.raises(SourceError):
        CsvSource.from_upload(b"\xff\xfe\x00\x01", "bad.csv", data_dir=tmp_path, max_bytes=LIMIT)


def test_purge_removes_uploads(tmp_path: Path) -> None:
    load(tmp_path, "a,b\n1,2\n")
    assert list((tmp_path / "uploads").glob("*.db"))
    purge_uploads(tmp_path)
    assert not list((tmp_path / "uploads").glob("*.db"))


def test_empty_header_cell_named_col(tmp_path: Path) -> None:
    assert columns(load(tmp_path, "a,,c\n1,2,3\n")) == ["a", "col", "c"]
