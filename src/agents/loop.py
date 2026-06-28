"""Agent loop — tool-calling orchestrator (PRD §5.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class OllamaClient(Protocol):
    """Narrow interface this module depends on."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any: ...


class MCPClient(Protocol):
    """Narrow interface this module depends on."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class SafetyGate(Protocol):
    """Narrow interface this module depends on."""

    def validate(self, sql: str) -> None: ...


@dataclass
class TurnResult:
    """Result of one agent turn."""

    answer: str
    sql: str | None
    tool_call_count: int
    exhausted: bool


class AgentLoop:
    """Orchestrates the tool-calling loop between Ollama and MCP.

    Args:
        ollama_client (OllamaClient): Sends chat+tools requests to Ollama.
        mcp_client (MCPClient): Forwards tool calls to the MCP server.
        safety_gate (SafetyGate): Validates SQL before execute_query reaches MCP.
        max_tool_calls (int): Circuit breaker — max tool calls per turn.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        mcp_client: MCPClient,
        safety_gate: SafetyGate,
        max_tool_calls: int,
    ) -> None:
        self._ollama = ollama_client
        self._mcp = mcp_client
        self._gate = safety_gate
        self._max_tool_calls = max_tool_calls

    async def run_turn(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> TurnResult:
        """Run one turn of the agent loop.

        Args:
            messages (list[dict[str, Any]]): Full message history for this turn.
            tools (list[dict[str, Any]]): Ollama tool schemas available to the model.

        Returns:
            TurnResult: Answer, sql, call count, and exhaustion flag.
        """
        history = list(messages)
        tool_call_count = 0

        while tool_call_count < self._max_tool_calls:
            response = await self._ollama.chat(history, tools)

            if not response.tool_calls:
                return TurnResult(
                    answer=response.text,
                    sql=None,
                    tool_call_count=tool_call_count,
                    exhausted=False,
                )

            for call in response.tool_calls:
                if call.name == "execute_query":
                    try:
                        self._gate.validate(call.arguments.get("sql", ""))
                    except Exception as exc:
                        tool_call_count += 1
                        history.append(
                            {
                                "role": "tool",
                                "name": call.name,
                                "content": f"blocked: {exc}",
                            }
                        )
                        continue
                try:
                    result = await self._mcp.call_tool(call.name, call.arguments)
                    content = str(result)
                except Exception as exc:
                    content = f"error: {exc}"
                tool_call_count += 1
                history.append({"role": "tool", "name": call.name, "content": content})

        return TurnResult(
            answer="",
            sql=None,
            tool_call_count=tool_call_count,
            exhausted=True,
        )
