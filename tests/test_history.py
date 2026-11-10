from pathlib import Path

from sqlwhisper.history import HistoryStore


def test_log_then_recent_newest_first(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.log("q1", "SELECT 1", 1, "sales.csv", ok=True)
    store.log("q2", "", 0, "db.local/shop", ok=False)

    first, second = store.recent()
    assert (first.question, first.ok, first.rows, first.source_label) == (
        "q2",
        False,
        0,
        "db.local/shop",
    )
    assert (second.question, second.sql, second.ok) == ("q1", "SELECT 1", True)
    assert first.id > second.id
    assert first.ts.endswith("+00:00")


def test_recent_is_capped(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    for i in range(25):
        store.log(f"q{i}", "SELECT 1", 1, "x", ok=True)
    assert len(store.recent()) == 20
    assert store.recent()[0].question == "q24"
    assert len(store.recent(3)) == 3


def test_persists_across_instances_and_creates_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "h.db"
    HistoryStore(path).log("q", "SELECT 1", 1, "x", ok=True)
    assert [e.question for e in HistoryStore(path).recent()] == ["q"]


def test_empty_history(tmp_path: Path) -> None:
    assert HistoryStore(tmp_path / "h.db").recent() == []


def test_quotes_and_unicode_are_stored_verbatim(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.log('it\'s "quoted" ünï', "SELECT 'a'", 1, "x", ok=True)
    assert store.recent()[0].question == 'it\'s "quoted" ünï'
