# SQLWhisper — Sprint 1: Core Engine

**Duration:** Week 1 (Days 1–7)
**Goal:** Full NL→SQL pipeline working end-to-end, Docker-deployable, with Streamlit UI

**Branch strategy:** `develop` base → feature branches → PR → CodeRabbit review → merge

---

## Sprint Goal

> *By end of sprint, a developer can run `docker compose up`, open `localhost:8501`, type a plain-English question, and get back a validated SQL query + result table — all running locally against their own PostgreSQL or SQLite database.*

---

## Backlog

### ✅ SW-1 — Project scaffold + config
**Branch:** `feature/project-scaffold`

- [x] `uv init sqlwhisper`, set up `pyproject.toml` with all dependencies
- [x] `pydantic-settings` config class: loads `config/config.yaml` + `.env.<APP_ENV>`
- [x] `config/config.yaml` schema: ollama block, databases block, app block — non-secrets only
- [x] `.env.example` with all required keys documented for `.env.development`, `.env.staging`, `.env.production`
- [x] `src/core/constants.py`: all magic strings, numbers, enums (`Dialect`, `BLOCKED_KEYWORDS`, prompt templates, limits)
- [x] `Makefile` with targets: `install`, `dev`, `lint`, `lint-fix`, `type`, `test`, `test-cov`, `check`, `run`, `cli`, `pc-install`, `pc`, `pc-all`, `pc-push`, `pc-run`, `pc-update`, `docker-up`, `docker-down`, `clean`
- [x] `pre-commit` config: trailing whitespace, end-of-file, mixed line endings, yaml/json/toml/ast checks, no-commit-to-branch, ruff, bandit, gitleaks, mypy strict
- [x] `[dependency-groups.dev]` in `pyproject.toml` (replaces deprecated `[tool.uv.dev-dependencies]`)
- [x] `/tests` using pytest with 99% coverage on `core/`
- [x] `.coderabbit.yaml`: full label set, path-based review instructions for all modules
- [x] Folder structure created: `src/core/`, `src/database/`, `src/llm/`, `src/validation/`
- [x] `README.md` stub with install instructions

**Notes:**
- Secrets (DB URLs) → `.env` only via `SecretStr`; never in `config.yaml`
- `APP_ENV` drives which `.env.<env>` file loads (development/staging/production)
- All constants centralised in `src/core/constants.py` — no magic values elsewhere
- `DatabaseSettings.url` is `SecretStr` — safe in logs and repr

---

### 🗄️ SW-2 — Database connector + schema cache
**Branch:** `feature/database-connector`

- [ ] `DatabaseConnector` class: connect via SQLAlchemy from config URL
- [ ] `inspect_schema()`: introspect all tables → `{table: {columns, pk, fk, row_count}}`
- [ ] Schema cache: stored in-memory on startup, refreshable via `--refresh-schema` flag
- [ ] `KeywordTableSelector`: extract nouns from question → fuzzy match → return top 5 tables
- [ ] Support dialects: `postgresql`, `sqlite`, `mysql` (use `Dialect` enum from constants)
- [ ] Unit test: schema introspection on a seeded SQLite test DB

---

### 🤖 SW-3 — Ollama client + prompt builder
**Branch:** `feature/llm-client`

- [ ] `OllamaClient`: POST to `/api/generate`, streaming response, extract SQL block
- [ ] Timeout handling (from `OllamaSettings.timeout_seconds`)
- [ ] `PromptBuilder`: assemble prompt using `PROMPT_TEMPLATE` from constants
- [ ] Correction prompt variant: uses `CORRECTION_PROMPT_TEMPLATE` from constants
- [ ] Strip markdown fences (` ```sql `) from LLM response before passing to validator
- [ ] Manual smoke test: 10 questions against local SQLite, log pass/fail

---

### ⚙️ SW-4 — SQL validator + retry loop
**Branch:** `feature/sql-validator`

- [ ] `SQLValidator.parse()`: `sqlglot` AST parse with dialect, surface syntax errors
- [ ] `SQLValidator.check_schema()`: extract table + column refs from AST, diff against cache
- [ ] `SQLValidator.check_safety()`: blocklist from `BLOCKED_KEYWORDS` constant — case-insensitive, full-token match
- [ ] `RetryOrchestrator`: loop max `MAX_RETRIES` times, correction prompt per error type, raise on exhaustion
- [ ] `QueryExecutor`: read-only SQLAlchemy session, hard-append `LIMIT {MAX_ROWS}` if missing
- [ ] `ResultSet` dataclass: rows, columns, execution_time_ms, sql_used
- [ ] Unit tests: valid SQL, bad column name, syntax error, blocked keyword, 3x retry exhaustion

---

### 🖥️ SW-5 — Streamlit UI
**Branch:** `feature/streamlit-ui`

- [ ] App scaffold: sidebar (DB selector, model info) + main query area
- [ ] DB selector dropdown populated from `config/config.yaml`
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
- [ ] History sidebar: last `QUERY_HISTORY_LIMIT` entries, click to re-run
- [ ] "Suggest queries" button → Ollama generates 5 starter questions from schema, shown as clickable chips
- [ ] Health check endpoint: `GET /health` returns Ollama status + DB connectivity

---

### 🐳 SW-7 — Docker + integration
**Branch:** `feature/docker`

- [ ] `Dockerfile`: multi-stage, `uv` install, non-root user, pinned base image
- [ ] `docker-compose.yml`: app + optional postgres service, healthchecks, restart policies
- [ ] Volume mount for `config/config.yaml` and `.env`
- [ ] `docker compose up` → UI live at `localhost:8501` in <60s
- [ ] End-to-end integration test: 20 questions, log accuracy rate
- [ ] Model benchmark: `sqlcoder:7b` vs `deepseek-coder:6.7b` on same 20 questions

---

## Definition of Done

- [ ] All feature branches merged to `develop` via PR
- [x] `pre-commit` hooks installed and passing (`pc-install` + `pc-all`)
- [ ] `docker compose up` works cleanly — UI live at `localhost:8501`
- [ ] 80%+ of 20 benchmark questions produce correct SQL on first attempt
- [ ] Validator catches 100% of blocked keywords before execution
- [ ] Retry loop resolves hallucinated columns in ≤2 retries
- [ ] No unhandled exceptions on Ollama timeout, bad SQL, or DB failure
- [ ] `ruff` + `mypy --strict` pass with zero errors
- [x] `core/` test coverage ≥ 99% (currently 99.03%)
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

| Decision                                                        | Reason                                                                                                                      |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `sqlglot` for validation over raw regex                         | AST-level parse catches structural errors regex misses; dialect-aware out of the box                                        |
| Keyword matching for table selection (not embeddings)           | Simpler, zero extra dependencies, sufficient for v0.1; embeddings deferred to Sprint 2                                      |
| `stdio` transport for MCP deferred                              | Core engine must be solid first; MCP is a thin wrapper, not a foundation                                                    |
| `sqlcoder:7b` as primary model                                  | Fine-tuned specifically for SQL generation; benchmark in Day 6 determines final default                                     |
| Read-only SQLAlchemy session enforced at executor level         | Safety belt independent of validator — LLM + validator both fail safe, executor is last guard                               |
| Hard `LIMIT 500` appended by executor                           | LLM ignores prompt rules inconsistently; enforcing at execution time is the only reliable guarantee                         |
| `uv` for dependency management                                  | Consistent with existing tooling; `[dependency-groups.dev]` used (replaces deprecated `[tool.uv.dev-dependencies]`)         |
| Streamlit over custom React UI                                  | Ships in day not week; focus is engine quality not UI fidelity in Sprint 1                                                  |
| Secrets via `SecretStr` + `.env` only                           | DB URLs contain credentials — must never appear in logs, `repr()`, or `config.yaml`                                         |
| All constants in `src/core/constants.py`                        | Single source of truth; eliminates magic values; `BLOCKED_KEYWORDS` and prompt templates version-controlled alongside logic |
| `APP_ENV`-driven env file loading                               | `.env.development` / `.env.staging` / `.env.production` — no config changes needed between environments                     |
| `.coderabbit.yaml` path instructions for `validation/safety.py` | Security-critical path; reviewers explicitly prompted to check blocklist bypass vectors and case sensitivity                |