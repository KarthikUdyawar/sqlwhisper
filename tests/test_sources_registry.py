from typing import Literal

import pytest
from sqlalchemy import Engine

from sqlwhisper.errors import SourceError
from sqlwhisper.models import Schema
from sqlwhisper.sources.registry import SourceRegistry


class Dummy:
    id = "abc"
    label = "dummy"
    dialect: Literal["sqlite"] = "sqlite"

    def engine(self) -> Engine:
        raise NotImplementedError

    def schema(self) -> Schema:
        return Schema(tables=[])


def test_add_then_get() -> None:
    registry = SourceRegistry()
    source = registry.add(Dummy())
    assert registry.get("abc") is source


def test_unknown_id_raises() -> None:
    with pytest.raises(SourceError, match="unknown source"):
        SourceRegistry().get("nope")
