from sqlwhisper.errors import SourceError
from sqlwhisper.sources.base import DataSource


class SourceRegistry:
    def __init__(self) -> None:
        self._items: dict[str, DataSource] = {}

    def add(self, source: DataSource) -> DataSource:
        self._items[source.id] = source
        return source

    def get(self, source_id: str) -> DataSource:
        try:
            return self._items[source_id]
        except KeyError:
            raise SourceError(f"unknown source: {source_id}") from None
