"""Tests for src/mcp_client/client.py.

Behavior 1 (this slice): connect() opens a session via the injected
factory, discovers its tools, and returns them mapped to Ollama's
tool-calling schema.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from mcp_client.client import MCPClient

# ---------------------------------------------------------------------------
# Fakes — stand in for mcp.types.Tool / mcp.ClientSession (the boundary).
# Structural match only: name, description, inputSchema / initialize, list_tools.
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(
        self, name: str, description: str | None, input_schema: dict[str, Any]
    ) -> None:
        self.name = name
        self.description = description
        self.inputSchema = input_schema


class _FakeListToolsResult:
    def __init__(self, tools: list[_FakeTool]) -> None:
        self.tools = tools


class _FakeSession:
    def __init__(self, tools: list[_FakeTool]) -> None:
        self._tools = tools
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def list_tools(self) -> _FakeListToolsResult:
        return _FakeListToolsResult(self._tools)


def _factory_for(session: _FakeSession) -> Any:
    @asynccontextmanager
    async def factory() -> AsyncIterator[_FakeSession]:
        yield session

    return factory


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_returns_tools_in_ollama_schema(self) -> None:
        session = _FakeSession(
            [
                _FakeTool(
                    "list_tables",
                    "List tables in the database",
                    {"type": "object", "properties": {}},
                ),
                _FakeTool(
                    "describe_table",
                    "Describe a table's columns",
                    {
                        "type": "object",
                        "properties": {"table": {"type": "string"}},
                        "required": ["table"],
                    },
                ),
            ]
        )
        client = MCPClient(_factory_for(session))

        tools = await client.connect()

        assert tools == [
            {
                "type": "function",
                "function": {
                    "name": "list_tables",
                    "description": "List tables in the database",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "describe_table",
                    "description": "Describe a table's columns",
                    "parameters": {
                        "type": "object",
                        "properties": {"table": {"type": "string"}},
                        "required": ["table"],
                    },
                },
            },
        ]

    @pytest.mark.asyncio
    async def test_initializes_session_before_listing_tools(self) -> None:
        session = _FakeSession([])
        client = MCPClient(_factory_for(session))

        await client.connect()

        assert session.initialized is True

    @pytest.mark.asyncio
    async def test_tool_with_no_description_maps_to_empty_string(self) -> None:
        session = _FakeSession([_FakeTool("ping", None, {"type": "object"})])
        client = MCPClient(_factory_for(session))

        tools = await client.connect()

        assert tools[0]["function"]["description"] == ""

    @pytest.mark.asyncio
    async def test_empty_server_returns_empty_list(self) -> None:
        client = MCPClient(_factory_for(_FakeSession([])))

        tools = await client.connect()

        assert tools == []
