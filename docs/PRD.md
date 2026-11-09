# SQLWhisper — Product Requirements Document

**Version:** 0.2.0 (supersedes 0.1.0)
**Stack:** FastAPI · Streamlit · Ollama · SQLAlchemy · sqlglot · pandas · Plotly · uv · Docker
**Default model:** `qwen2.5:7b-instruct` (env-configurable)
**Principles:** KISS, SOLID, test-first

---

## Problem

Non-technical users can't query their own data. Technical users waste time on boilerplate SQL. Cloud NL→SQL tools require sending schema and data to external APIs, which is a privacy risk.

SQLWhisper runs locally: plain English in, validated SQL + table + chart out. No data leaves the machine.

## Goal

Upload one CSV or connect a Postgres URL, ask a question in English, get:

- Validated, read-only SQL (with auto-correction on failure)
- Result table with CSV export
- Auto-picked chart

## Non-Goals (v0.2)

- Auth, multi-user, roles
- Write queries (INSERT / UPDATE / DELETE / DDL)
- Cloud LLM fallback, MCP server
- Embedding-based table selection
- Multiple CSVs / joins across uploads
- MySQL, `sqlite://` URLs, Excel
- Explain-result, suggest-queries, dashboards, scheduled reports

---

## Architecture

```bash
Streamlit UI ──HTTP──▶ FastAPI
                         │
   source (CSV | PG URL) │  question + last 3 Q/SQL pairs
                         ▼
                 Table selector (keyword, max 5)
                         ▼
                 Prompt builder
                         ▼
                 LLMClient (Ollama)  ◀─────┐
                         ▼                 │ correction prompt
                 Validator (sqlglot) ──fail┘ (max 2 retries)
                         ▼
                 Executor (read-only, LIMIT, timeout)
                         ▼
                 Chart picker (rules) → ResultSet
```

UI holds no logic beyond rendering. Plotly figures are built in the UI from a chart spec returned by the API.

## API

| Method | Path                   | Purpose                                            |
| ------ | ---------------------- | -------------------------------------------------- |
| GET    | `/health`              | Ollama reachable + model present                   |
| POST   | `/sources/csv`         | Multipart CSV → `{source_id, label, tables}`       |
| POST   | `/sources/url`         | `{url}` (Postgres) → `{source_id, label, tables}`  |
| GET    | `/sources/{id}/schema` | Tables, columns, types                             |
| POST   | `/query`               | `{source_id, question, context[]}` → `QueryResult` |
| GET    | `/history`             | Last 20 queries                                    |

`QueryResult`:

```json
{
  "sql": "SELECT ...",
  "columns": ["region", "total"],
  "rows": [["North", 120]],
  "row_count": 4,
  "truncated": false,
  "elapsed_ms": 412,
  "attempts": 1,
  "chart": {"type": "bar", "x": "region", "y": "total"}
}
```

Errors: `400` bad source/upload · `422` validation failed after retries (returns `last_sql` + error) · `502` Ollama unreachable · `504` query timeout.

---

## Features

### F1 — Sources

- **CSV:** one file, max 50 MB. Loaded with pandas into a SQLite file under `DATA_DIR`. Table name from filename, column names normalised to `snake_case`, deduplicated.
- **URL:** `postgresql://` only. Password never stored, logged, or written to history. The label shown in UI and history is `host/db`.
- Both implement one `DataSource` protocol, so the rest of the pipeline is source-agnostic.

### F2 — Schema + table selector

- Introspect via `sqlalchemy.inspect()`: tables, columns, types, PK/FK.
- If ≤5 tables: inject all. Otherwise keyword-match the question against table and column names, take the top 5.

### F3 — Prompt builder

- System prompt: dialect, schema subset, rules (single SELECT, alias tables, exact column names, no explanation, no fences).
- Context: last 3 Q/SQL pairs for follow-ups.
- Correction prompt: previous SQL + validator error.

### F4 — Validator (pure functions, sqlglot)

1. **Parse** with target dialect. Exactly one statement.
2. **Safety (AST):** root must be `SELECT` (CTEs and UNION allowed). Any write or DDL node anywhere in the tree → hard block, no retry.
3. **Schema:** every table and column ref must exist in the schema. Error names the closest valid column.

Parse and schema errors → correction prompt. Max 2 retries (3 attempts total), then `422`.

### F5 — Executor

Defense in depth. All four apply to every source:

1. Validator (F4)
2. Read-only connection: SQLite `mode=ro`; Postgres `default_transaction_read_only=on`
3. Hard `LIMIT` (default 500) applied to the AST if missing or larger
4. Statement timeout (default 15 s)

### F6 — Chart picker (deterministic)

| Result shape                | Chart   |
| --------------------------- | ------- |
| 1 row, or no numeric column | none    |
| date-like column + numeric  | line    |
| categorical + numeric       | bar     |
| 2 numeric columns           | scatter |
| anything else               | none    |

### F7 — UI + history

- Sidebar: source (CSV upload or URL, password-masked), Ollama status, schema explorer.
- Main: chat-style question box, SQL preview (collapsible), table, chart, CSV download.
- Errors shown inline: Ollama down, DB unreachable, validation exhausted (with last SQL), timeout.
- History: SQLite log `(id, question, sql, rows, source_label, ts, ok)`, last 20 in sidebar, click to re-run.

---

## SOLID mapping

| Principle | Application                                                                               |
| --------- | ----------------------------------------------------------------------------------------- |
| S         | One module, one job: `validator`, `executor`, `prompt`, `charts`, `history`               |
| O         | New source = new `DataSource` impl. New dialect = one entry in the dialect map            |
| L         | `CsvSource` and `PostgresSource` are interchangeable behind `DataSource`                  |
| I         | Small protocols: `LLMClient.complete()`, `DataSource.engine()` + `.schema()`              |
| D         | `pipeline` receives `LLMClient` and `DataSource` by injection. Tests use fakes, no Ollama |

KISS rule: plain functions where there is no state. A class only when it holds state or implements a protocol.

## Project structure

```bash
sqlwhisper/
├── src/sqlwhisper/
│   ├── settings.py      # pydantic-settings, env only
│   ├── models.py        # request/response schemas
│   ├── sources/
│   │   ├── base.py      # DataSource protocol
│   │   ├── csv.py
│   │   ├── postgres.py
│   │   └── registry.py  # source_id → DataSource (in memory)
│   ├── schema.py        # introspect + keyword selector
│   ├── llm.py           # LLMClient protocol + OllamaClient
│   ├── prompt.py
│   ├── validator.py
│   ├── pipeline.py      # generate → validate → retry
│   ├── executor.py
│   ├── charts.py        # result shape → chart spec
│   ├── history.py
│   ├── api.py           # FastAPI app
│   └── ui.py            # Streamlit app
├── tests/
├── docs/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── Makefile
└── pyproject.toml
```

Removed from repo: `main.py`, `requirements.txt` (uv only). The `chat-db-plotly` experiment is retired; only the Plotly idea carries over.

## Config (env only)

| Var                | Default                            |
| ------------------ | ---------------------------------- |
| `OLLAMA_URL`       | `http://localhost:11434`           |
| `OLLAMA_MODEL`     | `qwen2.5:7b-instruct`              |
| `OLLAMA_TIMEOUT_S` | `60`                               |
| `MAX_ROWS`         | `500`                              |
| `MAX_RETRIES`      | `2`                                |
| `QUERY_TIMEOUT_S`  | `15`                               |
| `MAX_UPLOAD_MB`    | `50`                               |
| `DATA_DIR`         | `./data`                           |
| `API_URL`          | `http://localhost:8000` (UI → API) |

## Dependencies

Runtime: `fastapi`, `uvicorn`, `python-multipart`, `httpx`, `sqlalchemy`, `psycopg[binary]`, `sqlglot`, `pandas`, `plotly`, `streamlit`, `pydantic-settings`.
Dev: `pytest`, `ruff`, `mypy`.

No `requests`, no `ollama` SDK: `httpx` covers it.

## Testing (test-first, red → green → refactor)

| Module      | Tests                                                                                                                        |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `validator` | valid select, CTE, UNION, syntax error, unknown table/column, INSERT/DROP/multi-statement, column named `update_date` passes |
| `schema`    | selector ≤5 tables returns all, >5 ranks by keyword                                                                          |
| `charts`    | one case per row of the F6 table                                                                                             |
| `executor`  | LIMIT injected/clamped, write attempt fails on read-only conn, timeout                                                       |
| `pipeline`  | fake `LLMClient`: pass first try, fix on retry, exhaust → error, safety block no retry                                       |
| `sources`   | CSV normalisation (spaces, dupes, dtypes), size limit, Postgres URL password never in label                                  |
| `api`       | `TestClient` happy path + each error code                                                                                    |

LLM is always faked in unit tests. One opt-in smoke test hits a real Ollama.

## Milestones

| #   | Deliverable                                        |
| --- | -------------------------------------------------- |
| M1  | Scaffold, settings, CI basics (ruff, mypy, pytest) |
| M2  | Sources + schema + selector                        |
| M3  | Validator + executor (no LLM yet)                  |
| M4  | LLM client + prompt + pipeline with retry          |
| M5  | FastAPI endpoints + history                        |
| M6  | Streamlit UI + charts                              |
| M7  | Docker, benchmark, README                          |

## Risks

| Risk                                  | Mitigation                                                      |
| ------------------------------------- | --------------------------------------------------------------- |
| Small model writes bad SQL            | Validator + retry; benchmark 4 installed models, pick default   |
| LLM ignores LIMIT                     | Executor enforces on AST                                        |
| Prompt injection via CSV cell content | Schema only goes in the prompt, never row data. Read-only guard |
| User pastes DB URL with password      | Masked input, never logged or stored                            |
| Dialect quirks                        | sqlglot dialect per source, tested for sqlite and postgres      |
| Large schema                          | Selector caps at 5 tables                                       |

## Success metrics

- ≥80% of 20 benchmark questions (fixed CSV) correct on first attempt
- 100% of non-SELECT statements blocked before execution
- Hallucinated column fixed in ≤2 retries on the benchmark
- `docker compose up` → UI live in <60 s
- No unhandled exception on Ollama down, bad SQL, bad URL, oversized upload
- `ruff` and `mypy --strict` clean, tests green

## Decision log

| Decision                                      | Reason                                                  |
| --------------------------------------------- | ------------------------------------------------------- |
| FastAPI + Streamlit split                     | API reusable by other clients later; UI stays dumb      |
| AST safety check, not keyword blocklist       | Fewer false positives, structurally complete            |
| Deterministic chart rules, not LLM chart JSON | Small models fail JSON often; rules are testable        |
| Postgres URL only                             | `sqlite:///` URL would expose host filesystem           |
| Env-only config                               | Sources are runtime inputs; a YAML file adds nothing    |
| Executor read-only, independent of validator  | Last guard if the validator ever has a bug              |
| `httpx` for Ollama                            | Already needed by the test client; one fewer dependency |
| No `--frozen` in Docker `uv sync`             | Lockfile state not guaranteed at build time             |
