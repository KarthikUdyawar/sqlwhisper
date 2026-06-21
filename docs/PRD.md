# SQLWhisper 2.0 — Product Requirements Document

|                      |                                                                                                                        |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Repo**             | [KarthikUdyawar/sqlwhisper](https://github.com/KarthikUdyawar/sqlwhisper) (`develop`)                                  |
| **Document version** | 2.0.0 — supersedes `docs/PRD.md` (v0.1.0)                                                                              |
| **Status**           | Draft — for engineering review                                                                                         |
| **Date**             | 2026-06-20                                                                                                             |
| **Author**           | Senior PM / Architect (this doc)                                                                                       |
| **Carries forward**  | Config system, `constants.py`, `BLOCKED_KEYWORDS`, tooling (`uv`, ruff, mypy strict, pre-commit, CodeRabbit) from v0.1 |
| **Replaces**         | Keyword-based table selection, single-shot generate-validate-retry loop, direct-SQLAlchemy execution path              |

---

## 0. Why this version exists

Sprint 1 (`v0.1.0`) shipped a working local engine: keyword table-selector → prompt builder → `sqlcoder:7b` → `sqlglot` AST validator → read-only SQLAlchemy executor → Streamlit UI. It works, but it has three structural ceilings the team already flagged in the Sprint 1 decision log:

1. **Static schema injection.** The keyword selector guesses up to 5 relevant tables per question. Wrong guesses mean wrong SQL, with no way for the model to ask for more schema.
2. **No standard DB interface.** `database/connector.py` and `database/executor.py` talk to SQLAlchemy directly. Adding a second data source (Grafana, a second Postgres, a future MCP-compatible tool) means rewriting the execution path each time.
3. **No conversation memory.** History is a write-only SQLite log. "Show their latest orders" after "Top 5 customers" doesn't resolve.

Sprint 1's own roadmap already named the fix: *"Sprint 2 — embedding-based table selection, MCP server (stdio/SSE)."* This PRD scopes that work, but the scope turned out larger than one sprint — it's a swap of the core reasoning loop (single-shot generate+retry → agentic tool-calling) and the addition of a real API layer — so it's versioned as **2.0** rather than an incremental sprint.

### What changes, at a glance

| Dimension          | v0.1 (current)                                                                | v2.0 (this PRD)                                                                                         |
| ------------------ | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Schema awareness   | Keyword/noun match, ≤5 tables injected into prompt                            | LLM calls `list_tables` / `describe_table` on demand                                                    |
| SQL generation     | Single-shot generate → `sqlglot` validate → correction-prompt retry (max 3)   | Agentic tool-calling loop; model retries naturally on tool errors                                       |
| DB interface       | Direct SQLAlchemy session                                                     | PostgreSQL MCP server via MCP client SDK                                                                |
| Safety enforcement | `sqlglot` AST + `BLOCKED_KEYWORDS` in app code                                | Same AST + blocklist, now gates the `execute_query` tool call, plus DB-level read-only role/transaction |
| Connections        | Static `config.yaml` + `.env` aliases, set at deploy time                     | Runtime `POST /connect` with a Postgres URL; static env-based connections still supported for local/dev |
| Backend            | None — Streamlit calls the engine in-process                                  | FastAPI async REST API (`/connect`, `/chat`, `/history`, `/disconnect`)                                 |
| Frontend           | Streamlit, tightly coupled to the engine                                      | Streamlit kept as a thin client over the API (Phase 1); React + Tailwind path documented (Phase 2)      |
| Memory             | SQLite write-only history log                                                 | `chat_history` table + conversation context replayed to the LLM for follow-ups                          |
| Model              | `sqlcoder:7b` / `deepseek-coder:6.7b` (completion-style, **no tool calling**) | `qwen3:8b`/`14b`, `llama3.3`, `gemma3` (tool-calling capable)                                           |
| Approval gate      | None                                                                          | Optional SQL approval step before `execute_query` runs                                                  |

Everything in `src/core/` (Settings, env precedence, secret handling, `BLOCKED_KEYWORDS`, bound constants) is retained as-is — it's infra-agnostic and 2.0 builds directly on it.

---

## 1. Executive Summary

SQLWhisper 2.0 turns the existing local NL→SQL engine into an **agentic, MCP-backed assistant**. Instead of guessing which 5 tables matter and hoping a single generated query is correct, the LLM is given tools (`list_tables`, `describe_table`, `execute_query`) and an Ollama tool-calling loop, so it inspects the schema it actually needs and iterates on errors itself. The PostgreSQL connection moves from a deploy-time config alias to a runtime `POST /connect` call, so one running instance can serve multiple databases and multiple chat sessions. A new FastAPI layer sits between the UI and the engine, which decouples the existing Streamlit frontend from the reasoning core and opens a path to a React frontend without touching the backend again. Every existing safety guarantee (AST parse, keyword blocklist, hard `LIMIT`, read-only execution) is preserved and re-applied at the new gating point — the `execute_query` tool call — plus a new DB-level read-only enforcement layer, since a tool-calling model is a strictly larger attack surface than a single-shot generator.

---

## 2. Goals

- Replace static keyword-based schema injection with on-demand schema discovery via MCP tools.
- Give the LLM tool calling instead of hand-rolled correction-prompt retries.
- Support multiple PostgreSQL connections at runtime, not just config-time aliases.
- Add a real backend API so the engine is reusable by more than one frontend.
- Add conversation memory so follow-up questions ("their latest orders") resolve correctly.
- Add an optional human-approval gate before any query executes.
- Keep the system **provably read-only** — this is non-negotiable and gets *more* layers in 2.0, not fewer.
- Keep the architecture extensible to non-Postgres MCP servers (Grafana, future internal tools) without another core rewrite.

## 3. Non-Goals (v2.0)

Carried over from v0.1, unchanged:

- No `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `COPY`, `GRANT`, `REVOKE` — ever, under any mode.
- No authentication / multi-tenant user accounts yet (single-tenant deployment assumption — see §13 Security).
- No cloud LLM fallback (stays 100% local via Ollama).

New for v2.0:

- No non-Postgres MCP servers shipped in this release (Grafana etc. is Future Roadmap, §19) — the architecture must support them later, but none ship now.
- No React frontend in this release — Streamlit is rebuilt against the new API; React is a documented Phase 2 option, not committed scope.
- No RBAC / per-user permissions (depends on auth, which is out of scope).

---

## 4. User Stories

| #    | As a...                           | I want to...                                                              | So that...                                                   |
| ---- | --------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| US-1 | Data analyst (non-technical)      | paste a Postgres URL and ask questions in plain English                   | I don't need to write SQL or know the schema upfront         |
| US-2 | Analyst mid-conversation          | ask "show their latest orders" after "top 5 customers"                    | I don't have to repeat full context every turn               |
| US-3 | DBA / platform owner              | guarantee the assistant can never write to the database                   | I can connect it to a production replica without fear        |
| US-4 | Team lead on a sensitive DB       | review the generated SQL and approve before it runs                       | I retain control over what executes against the database     |
| US-5 | Developer extending the tool      | plug in a new MCP server (e.g. Grafana) without rewriting the chat engine | the system stays extensible as more internal tools are added |
| US-6 | Analyst with several environments | switch between staging and prod Postgres connections in one session       | I don't need separate deployments per database               |
| US-7 | Engineer debugging an answer      | see the exact SQL, execution time, and row count behind every answer      | I can verify the assistant isn't hallucinating               |
| US-8 | Ops engineer                      | run the whole stack with `docker compose up`                              | deployment stays as simple as it was in v0.1                 |

---

## 5. Functional Requirements

### 5.1 Connection Management

- User submits a Postgres URL via `POST /connect` (UI: a connection form, not a config file edit).
- System validates the URL shape, then opens an MCP client session against the PostgreSQL MCP server scoped to that URL.
- On successful connect:
  - Verify connectivity (the MCP server's own handshake / a trivial `list_tables` call).
  - Discover schemas, tables, views, columns via MCP tools and cache the result (in-memory, keyed by `connection_id`).
  - Persist a **masked** connection record (`connections` table, §10) — never the raw URL.
- Static `.env`-defined connections (the v0.1 `SQLWHISPER_DATABASES__<ALIAS>__URL` pattern) remain supported for local/dev and CLI use; `/connect` is additive, not a replacement, for that path.
- `POST /disconnect` closes the MCP session and evicts the schema cache for that connection.

### 5.2 Chat Interface

User asks things like *"Top 10 customers by revenue"* or, as a follow-up, *"show their latest orders."* System must:

1. Load the conversation's recent history (`chat_history`, scoped by `connection_id` + session) and prepend it to the model context so pronouns/follow-ups resolve.
2. Run the **tool-calling agent loop** (§5.3) — the model decides whether/which tools to call.
3. Gate every `execute_query` tool call through the safety validator (§5.4) before it reaches MCP.
4. If approval mode is on, pause for user confirmation before execution (§5.5).
5. Execute via MCP, return rows to the model as a tool result.
6. Model produces a final natural-language answer once it has what it needs.
7. Return to the user: natural-language answer, the SQL actually executed, execution time, row count.
8. Persist the full turn to `chat_history`.

### 5.3 Tool Calling (replaces the v0.1 correction-prompt retry loop)

Ollama tool calling is used directly — no manual orchestration of "generate → parse error → re-prompt." The agent loop:

```
loop (max MAX_TOOL_CALLS_PER_TURN, default 8):
    response = ollama.chat(model, messages, tools=[list_tables, describe_table, execute_query])
    if response.tool_calls:
        for call in response.tool_calls:
            if call.name == "execute_query":
                validate_or_reject(call.args.sql)   # AST + blocklist, see 5.4
                if approval_mode: await_user_approval(call.args.sql)
            result = mcp_client.call_tool(call.name, call.args)
            messages.append(tool_result(call.id, result))
    else:
        return response.text   # final answer
raise ToolLoopExhausted()       # surfaced as a friendly error with the last SQL attempted
```

Tool schemas (unchanged contracts from the original spec, now formally MCP tool definitions):

**`list_tables`** → `{ "tables": ["customers", "orders", ...] }`

**`describe_table`** — input `{ "table": "orders" }` → `{ "columns": [{ "name": "id", "type": "integer" }, ...] }`

**`execute_query`** — input `{ "sql": "SELECT ... LIMIT 10" }` → `[{ "id": 1, ... }, ...]`

A hard cap (`MAX_TOOL_CALLS_PER_TURN`) prevents runaway loops on a confused model — on exhaustion, surface the error and the last attempted SQL, same UX contract as the old `RetryOrchestrator`.

### 5.4 Query Safety (re-applied, not replaced)

Before any `execute_query` call reaches MCP, reuse the existing v0.1 validator stack as a pre-tool-call gate:

- `sqlglot` AST parse (dialect = `postgresql`).
- `BLOCKED_KEYWORDS` check from `src/core/constants.py` — unchanged set: `DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, GRANT, REVOKE, EXEC, EXECUTE, CREATE, REPLACE, MERGE, CALL`.
- Allow-list: `SELECT`, `WITH`, `EXPLAIN`, `SHOW` only.
- Hard-append `LIMIT {MAX_ROWS}` if missing — same constant, same default (500).
- On rejection: return a tool **error** result to the model (not an exception that kills the turn) so the model can self-correct — this is the natural replacement for the old `CORRECTION_PROMPT_TEMPLATE`, since tool-call errors now serve that role.
- Hard blocks (blocklist hits) never retry silently — they're surfaced to the user as a blocked attempt, consistent with v0.1's "hard block, no retry on safety failures" rule.

This is layer 1 of 3 — see §13 for the full defense-in-depth stack (DB role + transaction-level enforcement are layers 2–3, new in 2.0).

### 5.5 SQL Approval Mode (new)

Optional, per-connection or per-session setting. When enabled:

```
Generated SQL:

SELECT ...

Approve? [Y/n]
```

- The agent loop pauses immediately after a `execute_query` call passes validation, before it's forwarded to MCP.
- User approves → execute normally, tool result flows back into the loop.
- User rejects → a structured "denied by user" tool result is returned to the model, which may try a different query or stop and explain.
- Default: **off** for local/dev connections, recommended **on** by default for any connection flagged as production in the connection form.

### 5.6 Conversation Memory (new)

- `chat_history` stores: user prompt, generated SQL, LLM answer, execution time, row count, timestamp — scoped by `connection_id`.
- The last *N* turns (configurable, default last 10) are replayed into the model's message list on every new turn, enabling follow-ups ("their," "that," "the same period").
- **Context overflow handling:** once replayed history + schema context approaches the model's context window, older turns are summarized into a single compact "conversation so far" message rather than dropped silently (see §12, error code `CTX_OVERFLOW`).

---

## 6. Non-Functional Requirements

| Category      | Requirement                                                                                                                                                           |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Performance   | P50 turn latency ≤ 5s, P95 ≤ 15s on a tool-calling-capable 8B model on consumer GPU hardware (target hardware: same class as v0.1's 8GB VRAM assumption)              |
| Reliability   | MCP session loss is recoverable — auto-reconnect once, then surface a clear error; no silent hangs                                                                    |
| Safety        | 100% of blocklisted statement types rejected before reaching MCP, verified by unit tests (carries forward the v0.1 bar: "validator catches 100% of blocked keywords") |
| Observability | Every tool call logged (tool name, args, duration, outcome) — structured logs, no raw connection strings ever logged                                                  |
| Code quality  | `ruff` + `mypy --strict` clean, ≥80% coverage gate (`pytest --cov-fail-under=80`, already enforced in `pyproject.toml`) — extend to all new modules                   |
| Portability   | `docker compose up` brings up the full stack (app + MCP server + Ollama reference) in <90s                                                                            |
| Extensibility | Adding a new MCP server must not require changes to `agents/` or `api/` — only a new entry in the MCP server registry/config                                          |

---

## 7. LLM Selection

`sqlcoder:7b`, the v0.1 default, is a completion-tuned SQL model — **it does not support Ollama tool calling**, so it cannot drive the new agent loop. The default model must change.

| Model                  | Tool calling | VRAM (approx)              | Notes                                                                                                                                                                                |
| ---------------------- | ------------ | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `qwen3:8b`             | ✅            | ~6–8 GB                    | **Recommended default.** Strong instruction-following + tool calling at a size that fits the same hardware class as v0.1's `sqlcoder:7b` target                                      |
| `qwen3:14b`            | ✅            | ~12–16 GB                  | Better reasoning on multi-step schema exploration; fallback for users with more VRAM, mirrors the v0.1 "default + fallback" pattern but inverted (bigger = better here, not smaller) |
| `llama3.3` (70B-class) | ✅            | High (≥40 GB or quantized) | Strongest reasoning, impractical for most local/dev setups; document as an option for server-class deployments only                                                                  |
| `gemma3`               | ✅            | Varies by size             | Viable lightweight alternative; needs the same benchmark pass as the others before recommending as default                                                                           |

**Recommendation:** ship `qwen3:8b` as `DEFAULT_MODEL`, `qwen3:14b` as `FALLBACK_MODEL` for higher-VRAM setups — same two-tier config pattern `core/config.py` already supports, just pointed at different models. Re-run the v0.1 "Day 6 model benchmark" practice (20 questions, accuracy + latency) against all four before locking the default in `config/config.yaml`.

---

## 8. MCP Architecture

**What MCP gives this system:** a standard protocol for "here are my tools, here's how to call them" between the LLM-orchestration layer and any backend (database, monitoring system, ticketing system, etc.), instead of SQLWhisper hand-rolling a bespoke executor per data source — which is exactly the v0.1 ceiling this PRD removes.

- **Tool discovery:** on `/connect`, the MCP client lists the PostgreSQL MCP server's available tools and capabilities; SQLWhisper maps `list_tables` / `describe_table` / `execute_query` to the Ollama tool schema format.
- **Tool calling:** Ollama returns structured tool-call requests; the orchestrator (§5.3) forwards them to the MCP client, which invokes the corresponding MCP server tool and returns the result.
- **Connection lifecycle:** one MCP client session per active `connection_id`. `POST /connect` opens it (stdio subprocess or SSE session against the PostgreSQL MCP server, pointed at the user's URL); `POST /disconnect` and session timeout both close it cleanly.
- **Transport:** recommend **stdio** for the default single-instance Docker deployment (simplest, matches v0.1's "ship in a day, not a week" philosophy) — document **SSE/HTTP** as the upgrade path when SQLWhisper needs to talk to a remote or multi-tenant MCP server (Future Roadmap, §19).
- **Read-only enforcement at the MCP layer:** the PostgreSQL MCP server should itself be configured against a read-only DB role (§13) — this is independent of and in addition to the AST/blocklist gate in §5.4.

---

## 9. Architecture

### 9.1 Frontend: Streamlit (kept) vs. React + Tailwind

|                  | Streamlit (Phase 1 — recommended)                                                                    | React + Tailwind (Phase 2 — optional)                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Build effort     | Near-zero — already exists, just repoint at the FastAPI API instead of calling the engine in-process | New build from scratch                                                                   |
| Fit for chat UX  | Adequate; approval-mode Y/n and streaming tool-call status are awkward in Streamlit's rerun model    | Natural fit for chat/streaming UX, tool-call status indicators, multi-connection tabs    |
| Time to ship 2.0 | Fast — matches v0.1's "ships in a day" decision rationale                                            | Slower; a real frontend build                                                            |
| Long-term polish | Limited                                                                                              | High — this is where a public-facing or multi-user product would eventually need to land |

**Recommendation:** Phase 1 keeps Streamlit, but it becomes a thin client calling `POST /connect` / `POST /chat` / `GET /history` instead of touching the engine directly. This is the single most important architectural move in 2.0: it's what makes a future React rewrite a frontend-only project instead of a full-stack rewrite.

### 9.2 Component Diagram

```mermaid
flowchart TD
    UI[Streamlit UI<br/>thin client] -->|REST| API[FastAPI<br/>async endpoints]
    API --> CM[Connection Manager<br/>connection_id → MCP session]
    API --> AGENT[Tool-Calling Agent Loop]
    AGENT --> OLLAMA[Ollama<br/>qwen3:8b, tool calling]
    AGENT --> GATE[Safety Gate<br/>sqlglot AST + BLOCKED_KEYWORDS]
    GATE --> MCPC[MCP Client SDK]
    CM --> MCPC
    MCPC <-->|stdio / SSE| MCPS[PostgreSQL MCP Server]
    MCPS -->|read-only role/txn| PG[(User's PostgreSQL DB)]
    API --> HIST[(chat_history)]
    API --> CONN[(connections)]
    AGENT --> HIST
```

### 9.3 Backend

- FastAPI, Python 3.12, async endpoints throughout — already a declared dependency in `pyproject.toml` (added in v0.1 but unused until now).
- `src/agents/` (new): the tool-calling loop, message assembly, context-window management.
- `src/mcp/` (new): MCP client wrapper, connection lifecycle, tool schema mapping.
- `src/llm/` (modified): drop `retry.py`'s correction-prompt logic (superseded by tool-call error feedback); keep/extend `client.py` for Ollama's chat + tools API instead of `/api/generate`.
- `src/validation/` (kept as-is): `parser.py`, `schema_check.py`, `safety.py` — now invoked as a pre-tool-call gate instead of a post-generation gate.
- `src/database/` (deprecated for the query path, see §11): `executor.py`/`selector.py`'s direct-SQLAlchemy logic is superseded by MCP; `connector.py`'s URL-validation logic is reused inside the new Connection Manager.

---

## 10. API Specification

### `POST /connect`

```json
// Request
{ "db_url": "postgresql://user:password@host:5432/db", "approval_mode": false }

// Response 200
{ "connection_id": "conn_8f2a", "connected": true, "tables": ["customers", "orders", "..."] }

// Response 400 — invalid URL / unreachable DB
{ "error_code": "CONN_INVALID", "message": "..." }
```

### `POST /chat`

```json
// Request
{ "connection_id": "conn_8f2a", "message": "Top 10 customers by revenue" }

// Response 200
{
  "answer": "...",
  "sql": "SELECT ...",
  "rows": 10,
  "execution_ms": 200,
  "tool_calls": 2,
  "pending_approval": false
}

// Response 200, approval mode pending
{ "pending_approval": true, "sql": "SELECT ...", "approval_token": "appr_91x" }
```

### `POST /chat/approve`

```json
// Request
{ "approval_token": "appr_91x", "approved": true }
```

### `GET /history?connection_id=conn_8f2a&limit=20`

Returns the persisted `chat_history` rows for that connection, most recent first.

### `POST /disconnect`

```json
// Request
{ "connection_id": "conn_8f2a" }
// Response 200
{ "disconnected": true }
```

### `GET /health` (retained from v0.1's planned health check)

Returns Ollama reachability + active MCP session count.

---

## 11. Database Design (application state — separate from the user's target Postgres DB)

Default: SQLite, anchored to project root, same pattern as v0.1's `HISTORY_DB_PATH` (`Path(__file__).resolve()...`, CWD-independent). Document a Postgres-backed option for multi-instance production deployments.

### `connections`

| Column          | Type       | Notes                                                                                                                               |
| --------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `id`            | text (PK)  | `connection_id`, e.g. `conn_8f2a`                                                                                                   |
| `name`          | text       | user-supplied label                                                                                                                 |
| `masked_url`    | text       | e.g. `postgresql://user:***@host:5432/db` — raw URL never persisted in plaintext                                                    |
| `encrypted_url` | bytea/text | Fernet-encrypted full URL, only if reconnect-without-re-entry is required; otherwise omit entirely and require re-entry per session |
| `approval_mode` | boolean    | default `false`                                                                                                                     |
| `created_at`    | timestamp  |                                                                                                                                     |

### `chat_history`

| Column          | Type                       | Notes                                                              |
| --------------- | -------------------------- | ------------------------------------------------------------------ |
| `id`            | integer (PK)               |                                                                    |
| `connection_id` | text (FK → connections.id) |                                                                    |
| `user_message`  | text                       |                                                                    |
| `sql_query`     | text                       | nullable — some turns resolve with no query (clarifying questions) |
| `llm_response`  | text                       |                                                                    |
| `rows_returned` | integer                    |                                                                    |
| `execution_ms`  | integer                    |                                                                    |
| `created_at`    | timestamp                  |                                                                    |

---

## 12. Error Handling

| Scenario                                        | Error code            | API response                                                                                     |
| ----------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------ |
| MCP server unavailable / fails to start         | `MCP_UNAVAILABLE`     | 503, retry guidance                                                                              |
| Invalid connection string                       | `CONN_INVALID`        | 400                                                                                              |
| DB unreachable from MCP server                  | `CONN_UNREACHABLE`    | 502                                                                                              |
| Query timeout                                   | `QUERY_TIMEOUT`       | 504, last SQL attempt included                                                                   |
| Blocked statement attempted                     | `SQL_BLOCKED`         | 200 with `blocked: true` — surfaced to user, no retry                                            |
| LLM/Ollama failure or timeout                   | `LLM_FAILURE`         | 502                                                                                              |
| Tool loop exhausted (`MAX_TOOL_CALLS_PER_TURN`) | `TOOL_LOOP_EXHAUSTED` | 200 with last SQL attempt + explanation                                                          |
| Network failure to Ollama or MCP                | `NETWORK_FAILURE`     | 503                                                                                              |
| Context window overflow                         | `CTX_OVERFLOW`        | handled internally via history summarization (§5.6); only surfaced if summarization itself fails |
| Approval denied                                 | n/a                   | 200, turn continues per §5.5                                                                     |

---

## 13. Security Design

Defense-in-depth — read-only is enforced at **three independent layers**, not one:

1. **App-layer gate** (existing, reused): `sqlglot` AST parse + `BLOCKED_KEYWORDS` before any `execute_query` tool call is forwarded.
2. **MCP-server-layer:** the PostgreSQL MCP server should connect using a dedicated **read-only DB role** (`GRANT SELECT` only, no `INSERT/UPDATE/DELETE/DDL` grants) — this is the new, stronger guarantee in 2.0 and should not be treated as optional.
3. **Transaction-layer:** wrap each `execute_query` in `SET TRANSACTION READ ONLY` (or the MCP server's equivalent) as a last-resort guard even if the role grants were ever misconfigured.

Other requirements:

- **SQL injection:** not applicable in the traditional sense (SQL is LLM-generated, not string-concatenated from user input) — but `execute_query` arguments are still validated structurally (AST parse) before execution, same as v0.1.
- **Prompt injection:** schema metadata and query *results* returned by MCP tools are untrusted data — they may contain text resembling instructions (e.g., a malicious row value). The system prompt must explicitly instruct the model to treat tool results as data only, never as instructions, and tool result content should never be eval'd or used to alter the tool-calling policy.
- **Tool abuse prevention:** `MAX_TOOL_CALLS_PER_TURN` cap (§5.3); rate limiting on `/chat` per connection; cap on rows/characters of tool-result content fed back into context.
- **Connection string handling:** never logged; never returned in API responses except masked; encrypted at rest if persisted for reconnect convenience (§11), otherwise not persisted at all.
- **Session isolation:** one MCP client session per `connection_id`; schema caches and chat history are strictly scoped by `connection_id` — no cross-connection leakage.
- **Multi-user security:** v2.0 ships **single-tenant** (no auth) — this is an explicit, documented gap, not an oversight. Production deployment guidance: run one instance per trusted user/team behind existing network-level access control until auth ships (Future Roadmap, §19).

---

## 14. Sequence Diagrams

### Connect

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant CM as Connection Manager
    participant MCP as MCP Client
    participant PG as Postgres MCP Server

    U->>API: POST /connect {db_url}
    API->>CM: validate + open session
    CM->>MCP: start session (stdio/SSE)
    MCP->>PG: handshake
    PG-->>MCP: tools available
    MCP-->>CM: list_tables()
    CM-->>API: connection_id, tables[]
    API-->>U: 200 {connection_id, tables}
```

### Chat turn (tool-calling loop)

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant A as Agent Loop
    participant O as Ollama
    participant G as Safety Gate
    participant M as MCP Server

    U->>API: POST /chat {message}
    API->>A: run_turn(history + message)
    loop until final answer or MAX_TOOL_CALLS
        A->>O: chat(messages, tools)
        O-->>A: tool_call(execute_query, sql)
        A->>G: validate(sql)
        G-->>A: ok / blocked
        A->>M: execute_query(sql)
        M-->>A: rows
        A->>O: tool_result(rows)
    end
    O-->>A: final text answer
    A-->>API: answer, sql, rows, execution_ms
    API-->>U: 200 {...}
```

### Approval mode

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant A as Agent Loop
    participant M as MCP Server

    A->>G: validate(sql) [passes]
    A-->>API: pending_approval {sql, approval_token}
    API-->>U: 200 {pending_approval: true, sql}
    U->>API: POST /chat/approve {approved: true}
    API->>A: resume
    A->>M: execute_query(sql)
    M-->>A: rows
    A-->>API: final answer
```

---

## 15. Folder Structure

```text
sqlwhisper/
├── config/
│   └── config.yaml              # [existing] now also lists mcp_servers + default model
├── docs/
│   ├── PRD.md                   # [existing] v0.1 — superseded by this doc
│   ├── PRD-2.0.md               # [new] this document
│   └── sprints/
├── src/
│   ├── core/                    # [existing, unchanged] config.py, constants.py
│   ├── api/                     # [new] FastAPI app, routers: connect, chat, history, health
│   ├── agents/                  # [new] tool-calling loop, context/history assembly
│   ├── mcp/                     # [new] MCP client wrapper, tool schema mapping, session lifecycle
│   ├── llm/                     # [modified] client.py → Ollama chat+tools API; retry.py removed
│   ├── validation/              # [existing, unchanged role] parser.py, schema_check.py, safety.py
│   ├── services/                # [new] connection manager, history service
│   ├── repositories/            # [new] connections + chat_history persistence
│   ├── schemas/                 # [new] Pydantic request/response models
│   ├── middleware/              # [new] rate limiting, request logging
│   ├── database/                # [deprecated for query path] connector.py URL-validation logic absorbed into services/; executor.py, selector.py removed
│   └── main.py                  # [existing] entrypoint, now boots FastAPI
├── app.py                       # [modified] Streamlit, now a thin REST client
├── tests/
├── Dockerfile / docker-compose.yml   # [modified] +mcp-postgres service
├── pyproject.toml               # [modified] +mcp SDK dependency
└── README.md                    # [modified] updated diagrams for 2.0
```

---

## 16. Deployment Architecture

```mermaid
flowchart LR
    subgraph Docker Compose
        APP[sqlwhisper-app<br/>FastAPI + Streamlit]
        MCPSVC[postgres-mcp-server]
        OLLAMA[ollama<br/>qwen3:8b]
    end
    APP --> MCPSVC
    APP --> OLLAMA
    MCPSVC -->|read-only role| EXTPG[(External / target Postgres)]
```

- `docker compose up` brings up the app, the Postgres MCP server, and (optionally) a reference Ollama container; an externally-hosted Ollama is also supported via config, same as v0.1's `base_url` override pattern.
- Healthchecks on all services; `restart: unless-stopped`, matching v0.1's Sprint 1 Docker requirements.
- Volume-mount `config/config.yaml` and `.env`, unchanged from v0.1.

---

## 17. Risks & Mitigations

| Risk                                                     | Mitigation                                                                                                                 |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `sqlcoder:7b` users can't tool-call                      | Default model changes to `qwen3:8b`; document the breaking change clearly in migration notes                               |
| Tool-calling reliability varies by model                 | Benchmark all four candidate models (§7) before locking the default; keep `MAX_TOOL_CALLS_PER_TURN` as a circuit breaker   |
| MCP server immaturity/compatibility                      | Pin a specific tested MCP server version; integration tests against it in CI                                               |
| Latency: multi-turn tool loop is slower than single-shot | Set and monitor P50/P95 budgets (§6); cap tool calls per turn                                                              |
| Context window overflow with growing schema + history    | History summarization (§5.6); `describe_table` results are not auto-injected for every table, only on demand               |
| Prompt injection via table/column names or row data      | Treat all tool results as untrusted data in the system prompt; never execute/interpret tool-result content as instructions |
| Connection string leakage                                | Mask everywhere in API/logs; encrypt at rest if persisted at all                                                           |
| Read-only enforcement single point of failure            | Three independent layers (§13) — app gate, DB role, transaction mode                                                       |
| No auth in this release                                  | Explicitly documented single-tenant deployment assumption; network-level access control until auth ships                   |

---

## 18. Success Metrics

- 80%+ of a 20-question benchmark set produce a correct final answer within `MAX_TOOL_CALLS_PER_TURN` (same bar v0.1 set for first-attempt accuracy, now measured end-to-end across the tool loop).
- 100% of blocklisted statement types rejected before reaching MCP — verified by unit tests covering every entry in `BLOCKED_KEYWORDS`.
- Follow-up questions ("their," "that") resolve correctly in 90%+ of a scripted multi-turn test set.
- `docker compose up` → working chat UI in under 90 seconds.
- Zero raw connection strings found in logs or API responses during a security review pass.

---

## 19. Future Roadmap (post-2.0)

- Additional MCP servers (Grafana, internal tooling) — the architecture in §8/§9 is built specifically so this doesn't require touching `agents/` or `api/`.
- Chart generation and dashboard generation from query results.
- CSV export (carried forward from v0.1's planned Streamlit feature).
- Scheduled reports; Slack and Telegram integrations.
- Authentication and role-based access control — unblocks true multi-tenant deployment.
- Query cost estimation and `EXPLAIN ANALYZE` support, surfaced alongside the existing execution-time metric.
- React + Tailwind frontend (Phase 2, §9.1) once the API layer has stabilized.
- Embedding-based table retrieval as a fallback/complement to MCP tool discovery for very large schemas (>50 tables, the threshold v0.1 already flags with `SCHEMA_MAX_TABLES_WARN`).

---

## 20. Open Decisions for the Team

These are the items this PRD recommends but does not unilaterally lock — flag for a short team decision before SW-2.0 kickoff:

1. **Default model:** `qwen3:8b` recommended — confirm after the benchmark pass (§7).
2. **MCP transport:** `stdio` recommended for v2.0 — confirm SSE isn't needed sooner if a remote/shared MCP server is already planned.
3. **Connection persistence:** encrypt-and-store vs. require re-entry every session — affects `connections.encrypted_url` (§11) and the overall security posture (§13).
4. **Approval mode default:** off everywhere vs. on-by-default for any connection not explicitly marked "dev/local."
