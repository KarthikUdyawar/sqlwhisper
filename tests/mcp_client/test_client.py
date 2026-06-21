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

from src.mcp_client.client import MCPClient

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


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_closes_session_after_connect(self) -> None:
        exited: list[bool] = []

        @asynccontextmanager
        async def factory() -> AsyncIterator[_FakeSession]:
            yield _FakeSession([])
            exited.append(True)  # runs on __aexit__

        client = MCPClient(factory)
        await client.connect()
        await client.disconnect()

        assert exited == [True]

    @pytest.mark.asyncio
    async def test_disconnect_before_connect_is_noop(self) -> None:
        client = MCPClient(_factory_for(_FakeSession([])))
        await client.disconnect()  # must not raise


class _FakeCallToolResult:
    def __init__(self, content: list[Any]) -> None:
        self.content = content


class _FakeSessionWithCallTool(_FakeSession):
    def __init__(self, tools: list[_FakeTool]) -> None:
        super().__init__(tools)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> _FakeCallToolResult:
        self.calls.append((name, arguments))
        return _FakeCallToolResult([{"rows": [1, 2, 3]}])


class TestCallTool:
    @pytest.mark.asyncio
    async def test_forwards_name_and_args_to_session(self) -> None:
        session = _FakeSessionWithCallTool([])
        client = MCPClient(_factory_for(session))
        await client.connect()

        result = await client.call_tool("execute_query", {"sql": "SELECT 1"})

        assert session.calls == [("execute_query", {"sql": "SELECT 1"})]
        assert result.content == [{"rows": [1, 2, 3]}]

    @pytest.mark.asyncio
    async def test_call_tool_before_connect_raises(self) -> None:
        client = MCPClient(_factory_for(_FakeSessionWithCallTool([])))

        with pytest.raises(RuntimeError, match="not connected"):
            await client.call_tool("list_tables", {})


class _DroppingSession(_FakeSessionWithCallTool):
    """Fails on first call_tool, succeeds on second."""

    def __init__(self, tools: list[_FakeTool]) -> None:
        super().__init__(tools)
        self._call_count = 0

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> _FakeCallToolResult:
        self._call_count += 1
        if self._call_count == 1:
            raise ConnectionError("session dropped")
        return await super().call_tool(name, arguments)


class TestReconnectOnDrop:
    @pytest.mark.asyncio
    async def test_reconnects_and_retries_on_session_error(self) -> None:
        session = _DroppingSession([])
        client = MCPClient(_factory_for(session))
        await client.connect()

        result = await client.call_tool("list_tables", {})

        assert session._call_count == 2
        assert result.content == [{"rows": [1, 2, 3]}]

    @pytest.mark.asyncio
    async def test_raises_if_retry_also_fails(self) -> None:
        calls: list[int] = []

        @asynccontextmanager
        async def factory() -> AsyncIterator[_FakeSession]:
            s = _FakeSessionWithCallTool([])

            # patch call_tool to always fail
            async def always_fail(
                name: str, arguments: dict[str, Any]
            ) -> _FakeCallToolResult:
                calls.append(1)
                raise ConnectionError("still down")

            s.call_tool = always_fail  # type: ignore[method-assign]
            yield s

        client = MCPClient(factory)
        await client.connect()

        with pytest.raises(ConnectionError, match="still down"):
            await client.call_tool("list_tables", {})

        assert len(calls) == 2  # tried twice
