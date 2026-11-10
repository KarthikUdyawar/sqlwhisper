import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fakes import FakeLLM
from sqlwhisper.api import create_app
from sqlwhisper.errors import LLMUnavailable
from sqlwhisper.models import Health
from sqlwhisper.settings import Settings
from sqlwhisper.sources.postgres import PostgresSource, parse_postgres_url

CSV = b"region,total\nNorth,10\nSouth,20\nNorth,5\nSouth,15\n"
GOOD = "SELECT region, SUM(total) AS total FROM sales GROUP BY region ORDER BY region"
FOREVER = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
UP = Health(ollama=True, model=True, model_name="qwen-test")


def make_client(
    tmp_path: Path,
    llm: FakeLLM | None = None,
    health: Health = UP,
    *,
    raise_server_exceptions: bool = True,
    **settings: Any,
) -> TestClient:
    cfg = Settings(_env_file=None, data_dir=tmp_path, **settings)
    app = create_app(cfg, llm=llm or FakeLLM(GOOD), health=lambda: health)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def upload(client: TestClient, content: bytes = CSV, name: str = "sales.csv") -> str:
    response = client.post("/sources/csv", files={"file": (name, content, "text/csv")})
    assert response.status_code == 200, response.text
    source_id: str = response.json()["source_id"]
    return source_id


def ask(client: TestClient, source_id: str, question: str = "total by region", **extra: Any) -> Any:
    return client.post("/query", json={"source_id": source_id, "question": question, **extra})


# ---- /health ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "health",
    [
        UP,
        Health(ollama=True, model=False, model_name="x"),
        Health(ollama=False, model=False, model_name="x"),
    ],
)
def test_health_reports_what_the_checker_says(tmp_path: Path, health: Health) -> None:
    response = make_client(tmp_path, health=health).get("/health")
    assert response.status_code == 200
    assert response.json() == health.model_dump()


# ---- sources ----------------------------------------------------------------------------


def test_csv_upload_happy_path(tmp_path: Path) -> None:
    response = make_client(tmp_path).post(
        "/sources/csv", files={"file": ("sales.csv", CSV, "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "sales.csv"
    assert body["tables"] == ["sales"]
    assert len(body["source_id"]) == 12


@pytest.mark.parametrize(
    ("content", "name", "fragment"),
    [
        (CSV, "sales.txt", "csv"),
        (b"", "sales.csv", "empty"),
        (b"a,b\n", "sales.csv", "no data rows"),
        (b"a,b\n" + b"1,2\n" * 300_000, "big.csv", "too large"),
    ],
)
def test_csv_upload_rejections_are_400(
    tmp_path: Path, content: bytes, name: str, fragment: str
) -> None:
    response = make_client(tmp_path, max_upload_mb=1).post(
        "/sources/csv", files={"file": (name, content, "text/csv")}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_source"
    assert fragment in response.json()["message"]


def test_csv_upload_without_a_file_is_422(tmp_path: Path) -> None:
    response = make_client(tmp_path).post("/sources/csv")
    assert response.status_code == 422
    assert response.json()["code"] == "bad_request"


@pytest.mark.parametrize("url", ["sqlite:///x.db", "not a url", "mysql://u:p@h/db"])
def test_bad_url_is_400(tmp_path: Path, url: str) -> None:
    response = make_client(tmp_path).post("/sources/url", json={"url": url})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_source"


def test_unreachable_url_is_400_and_does_not_echo_the_password(tmp_path: Path) -> None:
    response = make_client(tmp_path).post(
        "/sources/url", json={"url": "postgresql://bob:topsecret@127.0.0.1:1/shop"}
    )
    assert response.status_code == 400
    assert "topsecret" not in response.text
    assert "127.0.0.1/shop" in response.json()["message"]


def test_schema_endpoint(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get(f"/sources/{upload(client)}/schema")
    assert response.status_code == 200
    table = response.json()["tables"][0]
    assert table["name"] == "sales"
    assert [c["name"] for c in table["columns"]] == ["region", "total"]


def test_unknown_source_is_400(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/sources/nope/schema").status_code == 400
    response = ask(client, "nope")
    assert response.status_code == 400
    assert response.json()["code"] == "bad_source"


def test_uploads_are_purged_on_startup(tmp_path: Path) -> None:
    (tmp_path / "uploads").mkdir()
    stale = tmp_path / "uploads" / "old.db"
    stale.write_bytes(b"x")
    with make_client(tmp_path):
        assert not stale.exists()


# ---- /query -----------------------------------------------------------------------------


def test_query_happy_path_has_the_documented_shape(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = ask(client, upload(client))
    assert response.status_code == 200
    assert response.json() == {
        "sql": GOOD,
        "columns": ["region", "total"],
        "rows": [["North", 15], ["South", 35]],
        "row_count": 2,
        "truncated": False,
        "elapsed_ms": response.json()["elapsed_ms"],
        "attempts": 1,
        "chart": {"type": "bar", "x": "region", "y": "total"},
    }


def test_query_retry_reports_attempts(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeLLM("SELECT nope FROM sales", GOOD))
    assert ask(client, upload(client)).json()["attempts"] == 2


def test_query_passes_context_to_the_model(tmp_path: Path) -> None:
    llm = FakeLLM(GOOD)
    client = make_client(tmp_path, llm)
    context = [{"question": "total by region", "sql": GOOD}]
    ask(client, upload(client), "now only North", context=context)
    contents = [m["content"] for m in llm.calls[0][1]]
    assert contents == ["total by region", GOOD, "now only North"]


def test_unsafe_sql_is_422_with_last_sql(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeLLM("DROP TABLE sales"))
    response = ask(client, upload(client))
    assert response.status_code == 422
    assert response.json() == {
        "code": "unsafe_sql",
        "message": "only SELECT queries are allowed, got DROP",
        "last_sql": "DROP TABLE sales",
    }


def test_validation_exhausted_is_422_with_last_sql(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeLLM("SELECT nope FROM sales"), max_retries=1)
    response = ask(client, upload(client))
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["last_sql"] == "SELECT nope FROM sales"
    assert "nope" in body["message"]


def test_llm_down_is_502(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeLLM(LLMUnavailable("cannot reach Ollama (ConnectError)")))
    response = ask(client, upload(client))
    assert response.status_code == 502
    assert response.json() == {
        "code": "llm_unavailable",
        "message": "cannot reach Ollama (ConnectError)",
    }


def test_timeout_is_504(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeLLM(FOREVER), query_timeout_s=1)
    response = ask(client, upload(client))
    assert response.status_code == 504
    assert response.json()["code"] == "query_timeout"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"source_id": "x"},
        {"source_id": "x", "question": "   "},
        {"source_id": "x", "question": "q" * 2001},
    ],
)
def test_bad_query_body_is_422_without_echoing_input(tmp_path: Path, body: dict[str, str]) -> None:
    response = make_client(tmp_path).post("/query", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "bad_request"
    assert "input" not in response.json()
    assert "q" * 50 not in response.text


def test_unexpected_error_is_a_generic_500(tmp_path: Path) -> None:
    client = make_client(
        tmp_path, FakeLLM(RuntimeError("secret internals")), raise_server_exceptions=False
    )
    response = ask(client, upload(client))
    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "message": "unexpected error"}


# ---- /history ---------------------------------------------------------------------------


def test_history_logs_success_and_failure_newest_first(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeLLM(GOOD, "DROP TABLE sales"))
    source_id = upload(client)
    ask(client, source_id, "good one")
    ask(client, source_id, "bad one")

    entries = client.get("/history").json()
    assert [(e["question"], e["ok"], e["rows"]) for e in entries] == [
        ("bad one", False, 0),
        ("good one", True, 2),
    ]
    assert entries[0]["sql"] == "DROP TABLE sales"
    assert entries[1]["sql"] == GOOD
    assert {e["source_label"] for e in entries} == {"sales.csv"}


def test_history_is_capped_at_20_on_read(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    source_id = upload(client)
    for i in range(22):
        ask(client, source_id, f"question {i}")
    entries = client.get("/history").json()
    assert len(entries) == 20
    assert entries[0]["question"] == "question 21"


def test_no_credentials_in_history_responses_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client(tmp_path, FakeLLM("SELECT 1"))
    password = "hunter2-secret"
    source = PostgresSource(parse_postgres_url(f"postgresql://bob:{password}@127.0.0.1:1/shop"))
    client.app.state.registry.add(source)  # type: ignore[attr-defined]

    response = ask(client, source.id)  # database is unreachable
    assert response.status_code == 400
    history = client.get("/history")

    assert password not in response.text
    assert password not in history.text
    assert password.encode() not in (tmp_path / "history.db").read_bytes()
    assert password not in caplog.text
    assert history.json()[0]["source_label"] == "127.0.0.1/shop"
    assert history.json()[0]["ok"] is False
