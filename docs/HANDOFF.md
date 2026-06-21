# Handoff — SQLWhisper 2.0, §2 MCP client layer

Source of truth: `docs/PRD.md` (v2.0) §8, `docs/TODO.md` §2. Read both first.

## Current state

**§1 Core/Config — COMPLETE, verified.** `make check` fully green (ruff, ruff format, mypy, bandit, pydocstyle) + pytest 82/82, 81.67% coverage. Nothing left here.

**§2 MCP client layer — IN PROGRESS, partially unverified.**

- New package: `src/mcp_client/` — **not** `src/mcp/` as PRD §15 names it. Renamed because this repo's `src/` layout makes every subfolder a flat top-level import (`from core.config import ...`), so `src/mcp/` would shadow the real pypi `mcp` SDK inside its own code. Update PRD/README when this section ships.
- Design committed with user before coding (TDD plan-approval step):
  - `MCPClient.__init__(session_factory)` — `session_factory: Callable[[], AbstractAsyncContextManager[MCPSession]]`, injected dependency, never constructed internally.
  - `MCPSession` / `MCPTool` / `MCPListToolsResult` are narrow structural `Protocol`s matching only the subset of `mcp.ClientSession` actually used. Tests fake these Protocols — never mock the real SDK (boundary-only mocking).
  - `connection_id → session` lifecycle mapping deliberately **out of scope** for `MCPClient` — that belongs to the Connection Manager (PRD §7/§9.3). One `MCPClient` = one session.
- Behavior priority order (vertical slices, agreed with user):
  1. `connect()` → open session, discover tools, map to Ollama tool-calling schema — **implemented**, `src/mcp_client/client.py`
  2. `disconnect()` → close session, idempotent if already closed — **not started**
  3. `call_tool()` → forward name+args to session — **not started**
  4. dropped-session reconnect-once-then-raise on `call_tool()` — **not started**
- Integration test against a real containerized PG MCP server: deferred, separate from these unit-level slices.

## Blocking issue — fix first, before anything else in §2

Latest `make check` (user-run, pasted into chat): pre-commit fully green, pytest 82 passed — but `src/mcp_client/client.py` shows **0% coverage, 27/27 lines missed**. The behavior-1 test file was never collected, meaning it almost certainly never landed in the repo at the path given.

Root cause: test file was delivered at `tests/test_mcp_client.py` (flat), but this repo's actual test layout — confirmed from the coverage run — mirrors `src/`: `tests/core/test_config.py`, `tests/core/test_constants.py`. Flat `tests/test_*.py` was a wrong assumption from `docs/TODO.md`'s phrasing ("extend `tests/test_config.py`").

**Action:** move/add the test file to `tests/mcp_client/test_client.py` (matches `tests/core/` convention), re-run `make check`, confirm those 4 cases pass and coverage on `client.py` is no longer 0%. Only then is `connect()` actually done — don't take the green pre-commit run as proof; it only lints, it doesn't execute pytest on a file that was never present.

## Files delivered this session

- `config/config.yaml` — `mcp_servers` block added, merged by user, tests pass against it.
- `src/mcp_client/__init__.py` — package docstring, no logic.
- `src/mcp_client/client.py` — `MCPClient.connect()` + Protocols + `_to_ollama_tool()` mapping. Passed ruff/mypy/pydocstyle after one round of fixes (N815 noqa for `inputSchema` mirroring the SDK's wire field name, `AbstractAsyncContextManager` not `collections.abc.AsyncContextManager`, missing docstrings on Protocol stubs + `__init__` + package init).
- `tests/test_mcp_client.py` — 4 cases for `connect()`. **Wrong path** — needs to move to `tests/mcp_client/test_client.py`.
- `docs/TODO.md` — §1 checked off, §2 left unchecked with an inline status note (see file).

## Working conventions established this session

- TDD: strictly vertical slices, one behavior → one test → minimal impl → next. No horizontal slicing (all-tests-then-all-code rejected up front).
- Mocking only at the `MCPSession` Protocol boundary, never the real `mcp` SDK or our own collaborators.
- User does not want pytest executed in the agent sandbox ("don't waste tokens") — hand-trace RED/GREEN reasoning instead; user runs `make check` locally and pastes output back for verification.
- Caveman ultra mode active for conversational responses. Does not apply to code, docstrings, comments, or commit-style content (skill's own boundary rule) — those stay normal/professional.
- Before writing code for a new module/behavior: confirm interface + priority-ordered behavior list with user first (TDD "get approval on the plan" step) — done once already for §2 via `ask_user_input_v0`, worked well, repeat for future modules (§3 agents/, etc.).

## Next concrete step

1. Confirm `tests/mcp_client/test_client.py` exists and is green (user action).
2. Tracer-bullet `disconnect()`: closes the session via the stored `self._session_cm.__aexit__(None, None, None)`; no-op (not an error) if `self._session is None` already. One RED test, minimal GREEN impl, then stop and check in.
