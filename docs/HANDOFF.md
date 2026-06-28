# Handoff — SQLWhisper 2.0, §4 Safety Gate

Source of truth: `docs/PRD.md` (v2.0) §5.4, `docs/TODO.md` §4. Read both first.

## Current state

**§1 Core/Config — COMPLETE.** 92/92 tests, 96.91% coverage.

**§2 MCP client layer — COMPLETE (unit slices).** 100% coverage on `client.py`.

**§3 Agent loop — COMPLETE.** 98/98 tests, 97.45% total coverage.

- `src/agents/loop.py`: `AgentLoop` with `run_turn()` → `TurnResult`.
- `tests/agents/test_loop.py`: 6 cases covering all approved behaviors.
- `loop.py` 100% coverage, all linters/mypy/pydoclint clean.

**Known gap (not blocking §4):** `TurnResult.sql` always `None` — not yet extracted
from `execute_query` args on success. Track as follow-up after §4 or wire in §4.

**Infrastructure notes (carry forward from §2 handoff):**
- Every new `src/` package: add to `pyproject.toml` `packages` list + add `tests/<pkg>/__init__.py`.
- `tests/conftest.py` has `sys.path.insert` workaround for WSL editable-install `.pth` issue.
- pydoclint requires type hints in docstring arg list AND class-level docstring for `__init__` args (not on `__init__` method itself).

## Behaviors implemented in §3

1. Happy path — model returns final text, no tool calls
2. Single tool call → result fed back → final answer
3. `execute_query` → safety gate → blocked = tool error result (not exception)
4. Loop exhaustion at `max_tool_calls` → `exhausted=True`
5. Tool error (MCP raises) → error string as tool result → model self-corrects
6. History replay — prior messages passed through unchanged to Ollama

## Design of AgentLoop (for reference)

```python
# src/agents/loop.py
@dataclass
class TurnResult:
    answer: str
    sql: str | None      # ← always None currently; needs wiring
    tool_call_count: int
    exhausted: bool

class AgentLoop:
    def __init__(self, ollama_client, mcp_client, safety_gate, max_tool_calls) -> None
    async def run_turn(self, messages, tools) -> TurnResult
```

Protocols: `OllamaClient`, `MCPClient`, `SafetyGate` — all in `src/agents/loop.py`.
`SafetyGate.validate(sql: str) -> None` — raises on rejection, silent on pass.

## Next: §4 Safety gate re-pointing (PRD §5.4)

Re-point existing `src/validation/` to gate `execute_query` tool-call args.
The `SafetyGate` Protocol in `loop.py` already defines the interface — implement
a concrete class that calls the existing validator stack.

Behavior priority list for §4 (get user approval before starting):
1. `sqlglot` AST parse rejection → `SafetyGate.validate` raises
2. `BLOCKED_KEYWORDS` hit → raises
3. Allow-list pass (`SELECT`, `WITH`, `EXPLAIN`, `SHOW`) → silent
4. Hard-append `LIMIT {MAX_ROWS}` if missing, before forwarding
5. Rejection returns structured message (not bare exception string) for model

Confirm with user: implement concrete `SafetyGate` in `src/validation/gate.py`
satisfying the Protocol in `loop.py`, or rename/restructure existing `safety.py`?

## Working conventions

- TDD: vertical slices only. RED → GREEN → next. No horizontal slicing.
- Mock only at Protocol boundaries.
- User runs `make check` locally, pastes output.
- Caveman ultra mode for conversation. Normal for code/docstrings/commits.
- Every new `src/` package: add to `pyproject.toml` packages + `tests/<pkg>/__init__.py`.
- pydoclint: type hints required in docstring args; `__init__` args go on class docstring.
