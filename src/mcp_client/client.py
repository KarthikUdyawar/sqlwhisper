"""MCP client wrapper — thin, testable boundary over one MCP session.

Scope: open a session via an injected factory, discover its tools, and
map them into Ollama's tool-calling schema. Connection lifecycle keyed
by `connection_id` is NOT this module's job — that belongs to the
Connection Manager (PRD §7/§9.3), which owns one MCPClient per active
connection.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol


class MCPTool(Protocol):
    """Structural shape of one tool as returned by an MCP session's list_tools()."""

    name: str
    description: str | None
    inputSchema: dict[  # noqa: N815 -- mirrors mcp.types.Tool's wire field name
        str, Any
    ]


class MCPListToolsResult(Protocol):
    """Structural shape of the list_tools() response."""

    tools: list[MCPTool]


class MCPSession(Protocol):
    """Narrow structural interface this module depends on.

    Matches the subset of mcp.ClientSession actually used here — not the
    whole SDK — so tests fake this protocol, never the third-party package.
    """

    async def initialize(self) -> None:
        """Perform the MCP handshake with the connected server."""
        ...

    async def list_tools(self) -> MCPListToolsResult:
        """Return the tools exposed by the connected server."""
        ...


SessionFactory = Callable[[], AbstractAsyncContextManager[MCPSession]]


def _to_ollama_tool(tool: MCPTool) -> dict[str, Any]:
    """Map one MCP tool definition to Ollama's tool-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }


class MCPClient:
    """Wraps one MCP session.

    More behaviors (disconnect, call_tool, reconnect-once) land as
    separate TDD slices — this class grows incrementally, not upfront.

    Args:
        session_factory (SessionFactory): Opens one MCP session per call;
            no I/O happens until connect() is invoked.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session_cm: AbstractAsyncContextManager[MCPSession] | None = None
        self._session: MCPSession | None = None

    async def connect(self) -> list[dict[str, Any]]:
        """Open the session, discover tools, return them in Ollama schema form."""
        self._session_cm = self._session_factory()
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        result = await self._session.list_tools()
        return [_to_ollama_tool(tool) for tool in result.tools]
