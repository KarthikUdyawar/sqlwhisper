import pytest

from sqlwhisper.errors import SourceError
from sqlwhisper.sources.postgres import PostgresSource, parse_postgres_url


def test_label_is_host_slash_db_without_credentials() -> None:
    src = PostgresSource(parse_postgres_url("postgresql://bob:secret@db.local:5432/shop"))
    assert src.label == "db.local/shop"
    assert "secret" not in src.label
    assert "bob" not in src.label
    assert src.dialect == "postgres"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///x.db",
        "mysql://u:p@h/db",
        "postgresql+psycopg2://u:p@h/db",
        "not a url",
        "postgresql:///shop",
        "postgresql://u:p@h",
    ],
)
def test_rejects_bad_urls(url: str) -> None:
    with pytest.raises(SourceError):
        parse_postgres_url(url)


def test_unreachable_db_raises_without_leaking_password() -> None:
    with pytest.raises(SourceError, match="could not connect") as exc:
        PostgresSource.from_url("postgresql://bob:topsecret@127.0.0.1:1/shop")
    assert "topsecret" not in str(exc.value)
