# Handoff — SQLWhisper 2.0, §3 Agent loop

Source of truth: `docs/PRD.md` (v2.0) §5.3, `docs/TODO.md` §3. Read both first.

## Current state

**§1 Core/Config — COMPLETE.** 92/92 tests, 96.91% coverage.

**§2 MCP client layer — COMPLETE (unit slices).** `make check` fully green.

- `src/mcp_client/client.py`: `MCPClient` with `connect()`, `disconnect()`, `call_tool()`, reconnect-once-then-raise. 100% coverage.
- `tests/mcp_client/test_client.py`: 10 cases across 4 behaviors.
- Deferred (not blocking §3): PG MCP server wiring, `connection_id` lifecycle, integration test.

**Infrastructure fixes landed this session (not in PRD scope):**
- `pyproject.toml`: `[tool.hatch.build.targets.wheel]` needed `packages = ["src/core", "src/mcp_client"]` + `sources = ["src"]` — hatchling wasn't exposing `src/` subpackages as top-level imports.
- `tests/core/__init__.py` + `tests/mcp_client/__init__.py` added — missing `__init__.py` caused namespace collision (`core` test package shadowing `core` src package).
- `tests/conftest.py`: `sys.path.insert(0, str(Path(__file__).parent.parent / "src"))` before project imports — WSL `/mnt/d/` filesystem causes editable install `.pth` file to be written without trailing newline, making Python skip the entry.
- Every new `src/` subpackage needs adding to `packages` list in `pyproject.toml` + its own `tests/<pkg>/__init__.py`.

**§3 Agent loop — NOT STARTED.**

## Design decisions for §3 (confirm with user before coding)

Proposed interface:

```python
# src/agents/loop.py
class AgentLoop:
    def __init__(
        self,
        ollama_client: OllamaClient,
        mcp_client: MCPClient,
        safety_gate: SafetyGate,
        max_tool_calls: int,
    ) -> None: ...

    async def run_turn(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> TurnResult: ...
```

`TurnResult` — proposed:
```python
@dataclass
class TurnResult:
    answer: str
    sql: str | None
    tool_call_count: int
    exhausted: bool  # True if hit MAX_TOOL_CALLS_PER_TURN
```

Behavior priority order (vertical slices, get user approval before starting):
1. Happy path — model returns final text with no tool calls
2. Single tool call → result fed back → final answer
3. `execute_query` routed through safety gate before MCP (blocked → tool error result, not exception)
4. Loop exhaustion at `MAX_TOOL_CALLS_PER_TURN` → `exhausted=True` in `TurnResult`
5. Tool error → model receives error as tool result, self-corrects next iteration
6. Conversation history replay (last N turns prepended to messages)

## Working conventions

- TDD: vertical slices only. One RED test → minimal GREEN → next. No horizontal slicing.
- Mock only at Protocol boundaries — `OllamaClient`, `MCPClient`, `SafetyGate` all injected, faked in tests via structural Protocols (same pattern as `MCPSession`).
- User runs `make check` locally, pastes output. No pytest in agent sandbox.
- Caveman ultra mode for conversation. Normal for code/docstrings/commits.
- Get user approval on interface + behavior priority list before writing first RED test.
- Every new `src/` package: add to `pyproject.toml` `packages` list + add `tests/<pkg>/__init__.py`.

## Next concrete step

Present behavior priority list to user (above), get approval or adjustments, then write RED test for behavior 1 (happy path — no tool calls).
