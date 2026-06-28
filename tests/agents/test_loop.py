# tests/agents/test_loop.py
"""AgentLoop — behavior 1: happy path (no tool calls)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agents.loop import AgentLoop, TurnResult

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeOllamaResponse:
    text: str
    tool_calls: list[Any]


class _FakeOllamaClient:
    """Fake OllamaClient: returns a canned response with no tool calls."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> _FakeOllamaResponse:
        return _FakeOllamaResponse(text=self._text, tool_calls=[])


class _FakeMCPClient:
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        raise AssertionError("MCP must not be called in happy path")


class _FakeSafetyGate:
    def validate(self, sql: str) -> None:
        raise AssertionError("SafetyGate must not be called in happy path")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_answer_with_no_tool_calls() -> None:
    """Final text answer, zero tool calls → TurnResult fully populated."""
    loop = AgentLoop(
        ollama_client=_FakeOllamaClient("Here are the top 10 customers."),
        mcp_client=_FakeMCPClient(),
        safety_gate=_FakeSafetyGate(),
        max_tool_calls=8,
    )

    result = await loop.run_turn(
        messages=[{"role": "user", "content": "Top 10 customers by revenue"}],
        tools=[],
    )

    assert isinstance(result, TurnResult)
    assert result.answer == "Here are the top 10 customers."
    assert result.sql is None
    assert result.tool_call_count == 0
    assert result.exhausted is False


@dataclass
class _FakeOllamaResponseWithTool:
    text: str
    tool_calls: list[Any]


@dataclass
class _FakeToolCall:
    name: str
    arguments: dict[str, Any]


class _FakeOllamaClientWithOneTool:
    """First call returns a tool call; second returns final answer."""

    def __init__(
        self, tool_name: str, tool_args: dict[str, Any], final_text: str
    ) -> None:
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._final_text = final_text
        self._call_count = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        self._call_count += 1
        if self._call_count == 1:
            return _FakeOllamaResponseWithTool(
                text="",
                tool_calls=[_FakeToolCall(self._tool_name, self._tool_args)],
            )
        return _FakeOllamaResponseWithTool(text=self._final_text, tool_calls=[])


class _FakeMCPClientRecording:
    """Records calls, returns canned result."""

    def __init__(self, result: Any) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._result = result

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return self._result


@pytest.mark.asyncio
async def test_single_tool_call_result_fed_back_and_final_answer_returned() -> None:
    """One tool call → result appended → Ollama returns final text."""
    mcp = _FakeMCPClientRecording(result=[{"id": 1, "name": "Acme"}])

    loop = AgentLoop(
        ollama_client=_FakeOllamaClientWithOneTool(
            tool_name="list_tables",
            tool_args={},
            final_text="There is one table: customers.",
        ),
        mcp_client=mcp,
        safety_gate=_FakeSafetyGate(),
        max_tool_calls=8,
    )

    result = await loop.run_turn(
        messages=[{"role": "user", "content": "What tables exist?"}],
        tools=[],
    )

    assert result.answer == "There is one table: customers."
    assert result.tool_call_count == 1
    assert result.sql is None
    assert result.exhausted is False
    assert mcp.calls == [("list_tables", {})]


class _BlockingSafetyGate:
    """Raises on any SQL."""

    def validate(self, sql: str) -> None:
        raise ValueError(f"blocked: {sql}")


class _FakeOllamaClientWithExecuteQuery:
    """First call: execute_query tool call. Second: final answer."""

    def __init__(self, sql: str, final_text: str) -> None:
        self._sql = sql
        self._final_text = final_text
        self._call_count = 0
        self.last_messages: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        self._call_count += 1
        self.last_messages = list(messages)
        if self._call_count == 1:
            return _FakeOllamaResponseWithTool(
                text="",
                tool_calls=[_FakeToolCall("execute_query", {"sql": self._sql})],
            )
        return _FakeOllamaResponseWithTool(text=self._final_text, tool_calls=[])


@pytest.mark.asyncio
async def test_execute_query_blocked_by_safety_gate_returns_tool_error_not_exception() -> (
    None
):
    """Blocked SQL → tool error fed back to model, no exception raised, turn continues."""
    ollama = _FakeOllamaClientWithExecuteQuery(
        sql="DROP TABLE customers",
        final_text="I cannot run that query.",
    )
    mcp = _FakeMCPClientRecording(result=[])

    loop = AgentLoop(
        ollama_client=ollama,
        mcp_client=mcp,
        safety_gate=_BlockingSafetyGate(),
        max_tool_calls=8,
    )

    result = await loop.run_turn(
        messages=[{"role": "user", "content": "drop customers table"}],
        tools=[],
    )

    # Turn completes — no exception propagated
    assert result.answer == "I cannot run that query."
    assert result.exhausted is False

    # MCP never called — blocked before forwarding
    assert mcp.calls == []

    # Error fed back into message history so model can self-correct
    tool_messages = [m for m in ollama.last_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "blocked" in tool_messages[0]["content"].lower()


class _FakeOllamaClientAlwaysTools:
    """Always returns a tool call, never a final answer."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        return _FakeOllamaResponseWithTool(
            text="",
            tool_calls=[_FakeToolCall("list_tables", {})],
        )


@pytest.mark.asyncio
async def test_loop_exhaustion_sets_exhausted_flag() -> None:
    """Loop hits max_tool_calls → exhausted=True, no exception."""
    max_calls = 3
    mcp = _FakeMCPClientRecording(result=["customers"])

    loop = AgentLoop(
        ollama_client=_FakeOllamaClientAlwaysTools(),
        mcp_client=mcp,
        safety_gate=_FakeSafetyGate(),
        max_tool_calls=max_calls,
    )

    result = await loop.run_turn(
        messages=[{"role": "user", "content": "list tables forever"}],
        tools=[],
    )

    assert result.exhausted is True
    assert result.tool_call_count == max_calls
    assert len(mcp.calls) == max_calls


class _FakeOllamaClientToolThenCorrect:
    """First: tool call. Second: final answer. Records all messages seen."""

    def __init__(self, tool_name: str, final_text: str) -> None:
        self._tool_name = tool_name
        self._final_text = final_text
        self._call_count = 0
        self.all_messages: list[list[dict[str, Any]]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        self._call_count += 1
        self.all_messages.append(list(messages))
        if self._call_count == 1:
            return _FakeOllamaResponseWithTool(
                text="",
                tool_calls=[_FakeToolCall(self._tool_name, {"sql": "SELECT 1"})],
            )
        return _FakeOllamaResponseWithTool(text=self._final_text, tool_calls=[])


class _ErrorMCPClient:
    """Always raises on call_tool."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        raise RuntimeError("mcp timeout")


class _PassSafetyGate:
    """Allows all SQL through."""

    def validate(self, sql: str) -> None:
        pass


@pytest.mark.asyncio
async def test_tool_error_fed_back_as_tool_result_model_self_corrects() -> None:
    """MCP raises → error string in tool message → model gets second chance."""
    ollama = _FakeOllamaClientToolThenCorrect(
        tool_name="execute_query",
        final_text="Sorry, I could not execute that query.",
    )

    loop = AgentLoop(
        ollama_client=ollama,
        mcp_client=_ErrorMCPClient(),
        safety_gate=_PassSafetyGate(),  # passes validation
        max_tool_calls=8,
    )

    result = await loop.run_turn(
        messages=[{"role": "user", "content": "run a query"}],
        tools=[],
    )

    assert result.answer == "Sorry, I could not execute that query."
    assert result.exhausted is False

    # Second Ollama call must see a tool message containing the error
    second_call_messages = ollama.all_messages[1]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "mcp timeout" in tool_msgs[0]["content"]


@pytest.mark.asyncio
async def test_history_prepended_to_messages_for_follow_up() -> None:
    """Prior turns in messages list reach Ollama — loop doesn't strip history."""
    ollama = _FakeOllamaClientToolThenCorrect(
        tool_name="list_tables",
        final_text="Same customers as before.",
    )

    history = [
        {"role": "user", "content": "Top 5 customers"},
        {"role": "assistant", "content": "Here are the top 5."},
    ]
    current = {"role": "user", "content": "Show their orders"}

    loop = AgentLoop(
        ollama_client=ollama,
        mcp_client=_FakeMCPClientRecording(result=[]),
        safety_gate=_FakeSafetyGate(),
        max_tool_calls=8,
    )

    await loop.run_turn(messages=[*history, current], tools=[])

    first_call = ollama.all_messages[0]
    assert first_call[0] == history[0]
    assert first_call[1] == history[1]
    assert first_call[2] == current
