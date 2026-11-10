import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlwhisper.models import HistoryEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    sql TEXT NOT NULL,
    rows INTEGER NOT NULL,
    source_label TEXT NOT NULL,
    ts TEXT NOT NULL,
    ok INTEGER NOT NULL
)
"""


class HistoryStore:
    """Query log. Stores the source label (host/db), never a URL or credentials."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def log(self, question: str, sql: str, rows: int, source_label: str, *, ok: bool) -> None:
        ts = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO history (question, sql, rows, source_label, ts, ok) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (question, sql, rows, source_label, ts, int(ok)),
            )

    def recent(self, limit: int = 20) -> list[HistoryEntry]:
        with self._connect() as conn:
            found = conn.execute(
                "SELECT id, question, sql, rows, source_label, ts, ok "
                "FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            HistoryEntry(id=i, question=q, sql=s, rows=r, source_label=label, ts=ts, ok=bool(ok))
            for i, q, s, r, label, ts, ok in found
        ]

    def _connect(self) -> "_Connection":
        return _Connection(self._path)


class _Connection:
    """sqlite3 connection that commits on success AND closes (plain `with conn` only commits)."""

    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path)

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        with closing(self._conn):
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
