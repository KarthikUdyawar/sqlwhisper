# SQLWhisper — Sprint 1: Core Engine

**Duration:** Week 1 (Days 1–7)  
**Goal:** Full NL→SQL pipeline working end-to-end, Docker-deployable, with Streamlit UI

**Branch strategy:** `develop` base → feature branches → PR → CodeRabbit review → merge

---

## Sprint Goal

> *By end of sprint, a developer can run `docker compose up`, open `localhost:8501`, type a plain-English question, and get back a validated SQL query + result table — all running locally against their own PostgreSQL or SQLite database.*

---

## Backlog

### 🏗️ SW-1 — Project scaffold + config
**Branch:** `feature/project-scaffold`

- [ ] `uv init sqlwhisper`, set up `pyproject.toml` with all dependencies
- [ ] `pydantic-settings` config class: loads `config.yaml` + `.env`
- [ ] `config.yaml` schema: ollama block, databases block, app block
- [ ] `.env.example` with all required keys documented
- [ ] `pre-commit` config: ruff + mypy strict
- [ ] Folder structure created: `sqlwhisper/`, `database/`, `llm/`, `validation/`
- [ ] `README.md` stub with install instructions

---

### 🗄️ SW-2 — Database connector + schema cache
**Branch:** `feature/database-connector`

- [ ] `DatabaseConnector` class: connect via SQLAlchemy from config URL
- [ ] `inspect_schema()`: introspect all tables → `{table: {columns, pk, fk, row_count}}`
- [ ] Schema cache: stored in-memory on startup, refreshable via `--refresh-schema` flag
- [ ] `KeywordTableSelector`: extract nouns from question → fuzzy match → return top 5 tables
- [ ] Support dialects: `postgresql`, `sqlite`, `mysql`
- [ ] Unit test: schema introspection on a seeded SQLite test DB

---

### 🤖 SW-3 — Ollama client + prompt builder
**Branch:** `feature/llm-client`

- [ ] `OllamaClient`: POST to `/api/generate`, streaming response, extract SQL block
- [ ] Timeout handling (default 30s, config-driven)
- [ ] `PromptBuilder`: assemble prompt with dialect, schema subset, rules, question
- [ ] Prompt rules baked in: no writes, alias tables, LIMIT 500, exact column names only
- [ ] Correction prompt variant: accepts previous SQL + error message for retry
- [ ] Manual smoke test: 10 questions against local SQLite, log pass/fail

---

### ⚙️ SW-4 — SQL validator + retry loop
**Branch:** `feature/sql-validator`

- [ ] `SQLValidator.parse()`: `sqlglot` AST parse with dialect, surface syntax errors
- [ ] `SQLValidator.check_schema()`: extract table + column refs from AST, diff against cache
- [ ] `SQLValidator.check_safety()`: blocklist — `DROP`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `GRANT`, `EXEC`
- [ ] `RetryOrchestrator`: loop max 3x, build correction prompt per error type, raise on 3rd failure
- [ ] `QueryExecutor`: read-only SQLAlchemy session, hard-append `LIMIT 500` if missing
- [ ] `ResultSet` dataclass: rows, columns, execution_time_ms, sql_used
- [ ] Unit tests: valid SQL, bad column name, syntax error, blocked keyword, 3x retry exhaustion

---

### 🖥️ SW-5 — Streamlit UI
**Branch:** `feature/streamlit-ui`

- [ ] App scaffold: sidebar (DB selector, model info) + main query area
- [ ] DB selector dropdown populated from `config.yaml`
- [ ] Plain-English text area + "Run" button
- [ ] Loading spinner with elapsed time display
- [ ] Collapsible SQL preview (`st.code`, `sql` syntax highlight)
- [ ] Result table (`st.dataframe`, scroll, column types shown)
- [ ] CSV export button (`st.download_button`)
- [ ] Error states: Ollama unreachable, DB connection failure, validation failure, retry exhausted
- [ ] "Explain this result" button → sends SQL + result rows back to Ollama → NL summary shown

---

### 📋 SW-6 — Query history + stretch features
**Branch:** `feature/query-history`

- [ ] SQLite history log: `(id, question, sql, rows_returned, db_alias, timestamp, success)`
- [ ] History sidebar: last 20 entries, click to re-run
- [ ] "Suggest queries" button → Ollama generates 5 starter questions from schema, shown as clickable chips
- [ ] Health check endpoint: `GET /health` returns Ollama status + DB connectivity

---

### 🐳 SW-7 — Docker + integration
**Branch:** `feature/docker`

- [ ] `Dockerfile`: multi-stage, `uv` install, non-root user
- [ ] `docker-compose.yml`: app + optional postgres service
- [ ] Volume mount for `config.yaml` and `.env`
- [ ] `docker compose up` → UI live at `localhost:8501` in <60s
- [ ] End-to-end integration test: 20 questions, log accuracy rate
- [ ] Model benchmark: `sqlcoder:7b` vs `deepseek-coder:6.7b` on same 20 questions

---

## Definition of Done

- [ ] All feature branches merged to `develop` via PR
- [ ] `docker compose up` works cleanly — UI live at `localhost:8501`
- [ ] 80%+ of 20 benchmark questions produce correct SQL on first attempt
- [ ] Validator catches 100% of blocked keywords before execution
- [ ] Retry loop resolves hallucinated columns in ≤2 retries
- [ ] No unhandled exceptions on Ollama timeout, bad SQL, or DB failure
- [ ] `ruff` + `mypy --strict` pass with zero errors
- [ ] This sprint document (`SPRINT_1.md`) is checked off and moved to `docs/`
- [ ] No critical bugs remaining in scoped features

---

## Out of Scope (→ Sprint 2)

- MCP server + stdio/SSE transport
- Embedding-based table selection (replace keyword matcher)
- Auth / multi-user support
- Write query support (INSERT / UPDATE / DELETE)
- Cloud LLM fallback (OpenAI / Anthropic)
- VS Code / Claude Desktop integration
- Schema change detection (cache invalidation on DDL)

---

## Decision Log

| Decision                                                | Reason                                                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `sqlglot` for validation over raw regex                 | AST-level parse catches structural errors regex misses; dialect-aware out of the box                |
| Keyword matching for table selection (not embeddings)   | Simpler, zero extra dependencies, sufficient for v0.1; embeddings deferred to Sprint 2              |
| `stdio` transport for MCP deferred                      | Core engine must be solid first; MCP is a thin wrapper, not a foundation                            |
| `sqlcoder:7b` as primary model                          | Fine-tuned specifically for SQL generation; benchmark in Day 6 determines final default             |
| Read-only SQLAlchemy session enforced at executor level | Safety belt independent of validator — LLM + validator both fail safe, executor is last guard       |
| Hard `LIMIT 500` appended by executor                   | LLM ignores prompt rules inconsistently; enforcing at execution time is the only reliable guarantee |
| `uv` for dependency management                          | Consistent with existing tooling across all Karthik's projects                                      |
| Streamlit over custom React UI                          | Ships in day not week; focus is engine quality not UI fidelity in Sprint 1                          |