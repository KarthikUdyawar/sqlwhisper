import io
import re
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Self
from urllib.parse import quote

import pandas as pd
from sqlalchemy import URL, Engine, create_engine

from sqlwhisper.errors import SourceError
from sqlwhisper.models import Schema
from sqlwhisper.schema import introspect


def _snake(raw: str, prefix: str) -> str:
    s = re.sub(r"[^0-9a-z]+", "_", raw.lower()).strip("_")
    if not s:
        return prefix
    return f"{prefix}_{s}" if s[0].isdigit() else s


def _unique(names: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        candidate, n = name, 1
        while candidate in seen:
            n += 1
            candidate = f"{name}_{n}"
        seen.add(candidate)
        out.append(candidate)
    return out


def purge_uploads(data_dir: Path) -> None:
    """Called on API startup: uploads do not outlive the process."""
    shutil.rmtree(data_dir / "uploads", ignore_errors=True)


class CsvSource:
    dialect: Literal["sqlite"] = "sqlite"

    def __init__(self, source_id: str, label: str, path: Path) -> None:
        self.id = source_id
        self.label = label
        uri = f"sqlite:///file:{quote(str(path.resolve()))}?mode=ro&uri=true"
        self._engine = create_engine(uri)
        self._schema = introspect(self._engine)

    @classmethod
    def from_upload(cls, data: bytes, filename: str, *, data_dir: Path, max_bytes: int) -> Self:
        if not filename.lower().endswith(".csv"):
            raise SourceError("only .csv files are supported")
        if not data:
            raise SourceError("file is empty")
        if len(data) > max_bytes:
            raise SourceError(f"file too large (limit {max_bytes} bytes)")
        try:
            # Header read on its own: pandas would rename duplicates to "a.1" before we see them.
            raw = pd.read_csv(io.BytesIO(data), header=None, nrows=1, dtype=str)
            names = _unique(_snake(str(c), "col") for c in raw.iloc[0].fillna(""))
            df = pd.read_csv(io.BytesIO(data), header=0, names=names, index_col=False)
        except ValueError as e:  # empty, parse and decode errors all subclass ValueError
            raise SourceError(f"could not read CSV: {e}") from None
        if df.empty:
            raise SourceError("CSV has no data rows")

        name = Path(filename).name
        source_id = uuid.uuid4().hex[:12]
        path = data_dir / "uploads" / f"{source_id}.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = create_engine(URL.create("sqlite", database=str(path)))
        try:
            df.to_sql(_snake(Path(name).stem, "data"), writer, index=False)
        finally:
            writer.dispose()
        return cls(source_id, name, path)

    def engine(self) -> Engine:
        return self._engine

    def schema(self) -> Schema:
        return self._schema
