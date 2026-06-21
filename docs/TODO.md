# SQLWhisper 2.0 — TODO

Source of truth: `docs/PRD-2.0.md`. This file replaces `docs/sprints/` as the working task list — no sprint folders, just this checklist, kept current as work lands.

Each item links back to the PRD section it implements. Branch per item/group, PR → CodeRabbit review → merge into `develop`, same workflow as v0.1.

---

## Done — pre-flight config bugfixes (landed before the checklist below)

These surfaced while getting `make check` green on `develop`, before starting section 0. Not in PRD-2.0 scope, but they were blocking everything else, so fixed first.

- [x] Fix `DatabaseSettings.dialect` required-field mismatch — every `databases.<alias>` entry needs a matching `dialect` in `config/config.yaml` (non-secret) alongside its `url` in `.env` (secret). `config.yaml` had been left as `databases: {}` with a comment actively telling people not to add entries there, which contradicted how `DatabaseSettings`/`_assert_no_secrets_in_yaml` actually work. Added `default`/`local` dialect entries to `config.yaml`, fixed the misleading comment, and documented the pairing requirement in `.env.example`.
- [x] Add `tests/conftest.py` — `Settings()` / `Settings.from_yaml()` had no test isolation and were silently reading the real `config/config.yaml` and `.env*` files on every construction, so test results depended on the local dev environment's contents. Added an autouse fixture that redirects `_CONFIG_YAML` to a nonexistent path, clears `Settings.model_config["env_file"]`, and strips `SQLWHISPER_*` / `APP_ENV` from `os.environ` for the duration of each test.
- [ ] **Follow-up, not yet fixed:** `_merge_yaml_defaults` reads the module-level `_CONFIG_YAML` constant directly instead of respecting `Settings.from_yaml(path)`'s argument or a caller's `env_file` override. This is currently papered over by the `conftest.py` fixture above; worth a real fix later (e.g. thread the yaml path through instead of a hardcoded global) so it doesn't surprise someone outside of tests.

---

## 0. Cleanup & migration (do first)

- [x] Delete `docs/sprints/SPRINT_1.md` and the `docs/sprints/` folder
- [x] Move current `docs/PRD.md` → `docs/PRD-0.1-archive.md` (keep for history)
- [x] Add `docs/PRD-2.0.md` as the new active PRD
- [x] Update `README.md` roadmap section to point at this TODO instead of Sprint 1/2/3 language
- [x] Bump `pyproject.toml` version to `2.0.0-dev`
- [x] Add MCP client SDK + tool-calling-capable model deps to `pyproject.toml`; add to mypy `additional_dependencies`

---

## 1. Core / Config (PRD §7, §8)

- [ ] Add `mcp_servers` block to `config/config.yaml` (server command/args or SSE URL, per data source)
- [ ] Add `Dialect`/model constants for `qwen3:8b` (default) and `qwen3:14b` (fallback) in `src/core/constants.py`
- [ ] Add `MAX_TOOL_CALLS_PER_TURN` constant + min/max bounds (same pattern as existing `MAX_RETRIES`)
- [ ] Add `APPROVAL_MODE_DEFAULT` constant
- [ ] Keep `BLOCKED_KEYWORDS`, `MAX_ROWS`, secret-handling logic in `core/` untouched — confirm nothing here needs to change
- [ ] Unit tests for new config fields (extend `tests/test_config.py`, `tests/test_constants.py`)

## 2. MCP client layer — `src/mcp/` (new) (PRD §8)

- [ ] `MCPClient` wrapper: open/close session over stdio (default) and SSE (documented, not required for v2.0 launch)
- [ ] Tool discovery on connect: map MCP server tools → Ollama tool schema format
- [ ] `list_tables`, `describe_table`, `execute_query` tool definitions wired to the PostgreSQL MCP server
- [ ] Session lifecycle tied to `connection_id` (open on `/connect`, close on `/disconnect` or timeout)
- [ ] Reconnect-once-then-fail behavior on dropped MCP session
- [ ] Integration test against a real (containerized) PostgreSQL MCP server

## 3. Agent / tool-calling loop — `src/agents/` (new) (PRD §5.3)

- [ ] Implement the `loop until final answer or MAX_TOOL_CALLS_PER_TURN` orchestrator
- [ ] Wire Ollama chat-with-tools API (replaces `/api/generate` single-shot call)
- [ ] Route every `execute_query` tool call through the safety gate (§4 below) before forwarding to MCP
- [ ] Tool-loop-exhausted handling: surface last attempted SQL + friendly error (`TOOL_LOOP_EXHAUSTED`)
- [ ] Conversation memory: replay last N `chat_history` turns into the message list
- [ ] Context-window overflow handling: summarize older turns instead of dropping (`CTX_OVERFLOW`)
- [ ] Remove `src/llm/retry.py` (correction-prompt logic superseded by tool-call error feedback)
- [ ] Update `src/llm/client.py` to call Ollama's chat+tools endpoint instead of `/api/generate`
- [ ] Update `src/llm/prompt.py`: system prompt now describes available tools + explicitly instructs the model to treat tool results as untrusted data, not instructions (prompt-injection mitigation)
- [ ] Unit tests: happy path, tool error → self-correction, loop exhaustion, follow-up question resolution

## 4. Safety gate — `src/validation/` (kept, re-pointed) (PRD §5.4, §13)

- [ ] Re-point `parser.py` / `schema_check.py` / `safety.py` to gate `execute_query` tool-call args instead of post-generation SQL strings
- [ ] Confirm blocklist rejection returns a structured tool **error** (not an exception that kills the turn)
- [ ] Confirm hard blocks never enter a retry path — surfaced to user immediately, same as v0.1
- [ ] Auto-append `LIMIT {MAX_ROWS}` if missing, before forwarding to MCP
- [ ] Regression test: every entry in `BLOCKED_KEYWORDS` still rejected via the new tool-call gating path
- [ ] New test: prompt-injection-style row data in a tool result is never treated as an instruction

## 5. Approval mode (PRD §5.5)

- [ ] `pending_approval` state in the agent loop — pause before forwarding a validated `execute_query`
- [ ] `POST /chat/approve` endpoint to resume/deny
- [ ] Denial path: structured "denied by user" tool result fed back to the model
- [ ] Per-connection `approval_mode` flag, default off (confirm default per Open Decision #4 in PRD)

## 6. API layer — `src/api/` (new) (PRD §10)

- [ ] `POST /connect` — validate URL, open MCP session, discover schema, return `connection_id`
- [ ] `POST /chat` — run a turn through the agent loop
- [ ] `POST /chat/approve` — resume a pending-approval turn
- [ ] `GET /history?connection_id=...` — paginated chat history
- [ ] `POST /disconnect` — close MCP session, evict schema cache
- [ ] `GET /health` — Ollama reachability + active MCP session count
- [ ] Pydantic request/response models in `src/schemas/`
- [ ] Error responses mapped to the codes in PRD §12 (`CONN_INVALID`, `MCP_UNAVAILABLE`, `QUERY_TIMEOUT`, `SQL_BLOCKED`, `LLM_FAILURE`, `TOOL_LOOP_EXHAUSTED`, `NETWORK_FAILURE`, `CTX_OVERFLOW`)
- [ ] `src/middleware/`: request logging (no raw connection strings, ever), rate limiting on `/chat`

## 7. Persistence — `src/repositories/`, `src/services/` (new) (PRD §11)

- [ ] `connections` table: `id`, `name`, `masked_url`, `encrypted_url` (per Open Decision #3), `approval_mode`, `created_at`
- [ ] `chat_history` table: `id`, `connection_id`, `user_message`, `sql_query`, `llm_response`, `rows_returned`, `execution_ms`, `created_at`
- [ ] SQLite default, anchored to project root (same pattern as v0.1's `HISTORY_DB_PATH`); document Postgres upgrade path for prod
- [ ] Connection Manager service: `connection_id` → MCP session + schema cache mapping
- [ ] History service: write on every turn, read for `GET /history` and agent-loop context replay
- [ ] URL masking utility — confirm raw URL never appears in logs, API responses, or `repr()`

## 8. Deprecate v0.1 direct-DB path (PRD §9.3, §15)

- [ ] Remove `src/database/executor.py` (superseded by MCP `execute_query`)
- [ ] Remove `src/database/selector.py` (keyword table selection superseded by `list_tables`/`describe_table`)
- [ ] Fold any reusable URL-validation logic from `src/database/connector.py` into the new Connection Manager, then remove the rest
- [ ] Remove now-dead tests for the removed modules; confirm coverage gate (`--cov-fail-under=80`) still passes

## 9. Frontend — Streamlit thin client (PRD §9.1)

- [ ] Repoint `app.py` to call the FastAPI API instead of the in-process engine
- [ ] Connection form → `POST /connect`
- [ ] Chat box → `POST /chat`, render answer + SQL + execution time + row count
- [ ] Approval mode UI: Y/n prompt wired to `POST /chat/approve`
- [ ] History sidebar → `GET /history`
- [ ] Multi-connection support in the session (switch between active `connection_id`s)
- [ ] (Phase 2, not this release) Scope a React + Tailwind frontend against the now-stable API

## 10. Security (PRD §13)

- [ ] Document and provision a read-only Postgres role for the MCP server connection (`GRANT SELECT` only)
- [ ] Confirm `SET TRANSACTION READ ONLY` (or MCP server equivalent) wraps every `execute_query`
- [ ] Security review pass: grep logs/responses for raw connection strings — must be zero hits
- [ ] Document single-tenant/no-auth deployment assumption in README

## 11. Deployment (PRD §16)

- [ ] Add `postgres-mcp-server` service to `docker-compose.yml`
- [ ] Update `Dockerfile`/compose for FastAPI entrypoint (`main.py` boots the API, not just CLI)
- [ ] Healthchecks on app, MCP server, Ollama
- [ ] Confirm `docker compose up` → working chat UI in <90s
- [ ] Update `.env.example` with any new required keys (MCP server config, model names)

## 12. Docs

- [ ] Update `README.md` diagrams (architecture, validation pipeline, safety guarantees) for the MCP/tool-calling flow
- [ ] Update README quick-start for `/connect`-based runtime connections (vs. static `config.yaml` aliases)
- [ ] Document the three Open Decisions from PRD §20 once resolved (model, transport, persistence, approval default)

---

## Benchmarks before locking defaults (PRD §7, §18)

- [ ] Run the 20-question benchmark across `qwen3:8b`, `qwen3:14b`, `llama3.3`, `gemma3` — accuracy + latency
- [ ] Confirm 80%+ correct-answer rate within `MAX_TOOL_CALLS_PER_TURN` before declaring v2.0 done
- [ ] Confirm 100% blocklist rejection rate (regression suite)
- [ ] Scripted multi-turn test set for follow-up resolution — target 90%+
