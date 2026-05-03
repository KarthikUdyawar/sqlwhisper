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
**Branch:** `feature/project-scaffold` · **Status:** merged

- [x] `uv init sqlwhisper`, set up `pyproject.toml` with all dependencies
- [x] `[dependency-groups.dev]` in `pyproject.toml` (replaces deprecated `[tool.uv.dev-dependencies]`)
- [x] `pydantic-settings` config class: loads `config/config.yaml` + `.env.<APP_ENV>`
- [x] `config/config.yaml` schema: ollama block, databases block, app block — non-secrets only
- [x] `.env.example` with all required keys documented for `.env.development`, `.env.staging`, `.env.production`; all values quoted; correct `SQLWHISPER_<SECTION>__<KEY>` prefix throughout
- [x] `src/core/constants.py`: all magic strings, numbers, enums (`Dialect`, `BLOCKED_KEYWORDS`, prompt templates, limits); `HISTORY_DB_PATH` anchored to project root (CWD-independent)
- [x] `CORRECTION_PROMPT_TEMPLATE` includes `{dialect}`, `{schema_subset}`, `{question}` so LLM has full context on correction retries
- [x] `_deep_merge` in `config.py` — partial env-derived nested dicts no longer wipe sibling yaml keys
- [x] `Makefile` with targets: `install`, `dev`, `lint`, `lint-fix`, `type`, `test`, `test-cov`, `check`, `run`, `cli`, `pc-install`, `pc`, `pc-all`, `pc-push`, `pc-run`, `pc-update`, `docker-up`, `docker-down`, `clean`
- [x] `pre-commit` config: trailing whitespace, end-of-file, mixed line endings, yaml/json/toml/ast checks, no-commit-to-branch, ruff, bandit, gitleaks, mypy strict; all SW-2–5 deps pre-added to mypy `additional_dependencies`
- [x] `/tests` using pytest with 99% coverage on `core/` — 60 tests passing
- [x] `.coderabbit.yaml`: full label set, path-based review instructions for all modules
- [x] Folder structure created: `src/core/`, `src/database/`, `src/llm/`, `src/validation/`
- [x] `README.md` with architecture diagrams, quick start, config reference, dev workflow

**CodeRabbit findings resolved (PR review):**

| Finding                                                        | Fix                                                                       |
| -------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `CORRECTION_PROMPT_TEMPLATE` missing dialect/schema context    | Added `{dialect}`, `{schema_subset}`, `{question}` placeholders           |
| `HISTORY_DB_PATH` CWD-dependent bare filename                  | Anchored to `Path(__file__).resolve().parent.parent.parent`               |
| `_merge_yaml_defaults` shallow merge wiped nested yaml keys    | Replaced with `_deep_merge` recursive helper                              |
| `.env.example` wrong prefix `SQLWHISPER__*`                    | Fixed to `SQLWHISPER_<SECTION>__<KEY>` throughout                         |
| `.env.example` unquoted values                                 | All values now quoted                                                     |
| `config/config.yaml` comment wrong prefix                      | Fixed to `SQLWHISPER_<SECTION>__<KEY>`                                    |
| `config.py` docstring wrong prefix                             | Fixed to `SQLWHISPER_*`                                                   |
| `tests/test_config.py` hardcoded dialect list in parametrize   | Now uses `sorted(SUPPORTED_DIALECTS)`                                     |
| mypy `additional_dependencies` missing SW-2–5 packages         | Added `sqlglot`, `httpx`, `pandas`, `pandas-stubs`, `ollama`, `streamlit` |
| `README.md` project-structure block missing language specifier | Changed opening fence to ` ```text `                                      |

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

- [ ] `OllamaClient`: POST to `OLLAMA_GENERATE_PATH`, streaming response, extract SQL block
- [ ] Timeout handling (from `OllamaSettings.timeout_seconds`); all HTTP calls must set explicit timeout
- [ ] `PromptBuilder`: assemble prompt using `PROMPT_TEMPLATE` from constants
- [ ] Correction prompt: uses `CORRECTION_PROMPT_TEMPLATE` — pass `dialect`, `schema_subset`, `question`, `sql`, `error`
- [ ] Strip markdown fences (` ```sql `) from LLM response before passing to validator
- [ ] Empty LLM response must raise, not pass empty string to validator
- [ ] Manual smoke test: 10 questions against local SQLite, log pass/fail

---

### ⚙️ SW-4 — SQL validator + retry loop
**Branch:** `feature/sql-validator`

- [ ] `SQLValidator.parse()`: `sqlglot` AST parse with dialect, surface syntax errors
- [ ] `SQLValidator.check_schema()`: extract table + column refs from AST (not raw string), diff against cache
- [ ] `SQLValidator.check_safety()`: blocklist from `BLOCKED_KEYWORDS` — case-insensitive, full-token match (not substring)
- [ ] `check_safety()` result must never enter retry loop — hard block, raise immediately
- [ ] `RetryOrchestrator`: loop max `MAX_RETRIES` times, correction prompt per error type, raise on exhaustion with last SQL shown
- [ ] `QueryExecutor`: read-only SQLAlchemy session, hard-append `LIMIT {MAX_ROWS}` if missing — use constant, not hardcoded 500
- [ ] `ResultSet` dataclass: rows, columns, execution_time_ms, sql_used
- [ ] Unit tests: valid SQL, bad column name, syntax error, every keyword in `BLOCKED_KEYWORDS`, 3x retry exhaustion

---

### 🖥️ SW-5 — Streamlit UI
**Branch:** `feature/streamlit-ui`

- [ ] App scaffold: sidebar (DB selector, model info) + main query area
- [ ] DB selector dropdown populated from `config/config.yaml`
- [ ] Plain-English text area + "Run" button
- [ ] Loading spinner with elapsed time display (use `ELAPSED_TIME_DECIMALS` constant)
- [ ] Collapsible SQL preview (`st.code`, `sql` syntax highlight)
- [ ] Result table (`st.dataframe`, scroll, column types shown)
- [ ] CSV export button (`st.download_button`) — filename from `CSV_EXPORT_FILENAME` constant
- [ ] Error states: Ollama unreachable, DB connection failure, validation failure, retry exhausted
- [ ] "Explain this result" button → sends SQL + result rows back to Ollama → NL summary shown

---

### 📋 SW-6 — Query history + stretch features
**Branch:** `feature/query-history`

- [ ] SQLite history log: `(id, question, sql, rows_returned, db_alias, timestamp, success)` — written to `HISTORY_DB_PATH`
- [ ] History sidebar: last `QUERY_HISTORY_LIMIT` entries, click to re-run
- [ ] "Suggest queries" button → Ollama generates 5 starter questions from schema, shown as clickable chips
- [ ] Health check endpoint: `GET /health` returns Ollama status + DB connectivity

---

### 🐳 SW-7 — Docker + integration
**Branch:** `feature/docker`

- [ ] `Dockerfile`: multi-stage, `uv` install, non-root user, pinned base image, no secrets in `ENV`/`RUN`
- [ ] `docker-compose.yml`: app + optional postgres service, healthchecks, `restart: unless-stopped`
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
- [ ] Validator catches 100% of `BLOCKED_KEYWORDS` before execution
- [ ] Retry loop resolves hallucinated columns in ≤2 retries
- [ ] No unhandled exceptions on Ollama timeout, bad SQL, or DB failure
- [ ] `ruff` + `mypy --strict` pass with zero errors
- [x] `core/` test coverage ≥ 99% (currently 99.11%, 60 tests)
- [ ] This sprint document checked off and moved to `docs/sprints/`
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
| `uv` + `[dependency-groups.dev]`                        | Consistent tooling; replaces deprecated `[tool.uv.dev-dependencies]`                                |
| Streamlit over custom React UI                          | Ships in day not week; focus is engine quality not UI fidelity in Sprint 1                          |
| Secrets via `SecretStr` + `.env` only                   | DB URLs contain credentials — must never appear in logs, `repr()`, or `config.yaml`                 |
| All constants in `src/core/constants.py`                | Single source of truth; `BLOCKED_KEYWORDS` and prompt templates version-controlled alongside logic  |
| `APP_ENV`-driven env file loading                       | `.env.development` / `.env.staging` / `.env.production` — no config changes between environments    |
| `CORRECTION_PROMPT_TEMPLATE` includes dialect + schema  | LLM needs column names and SQL flavour to resolve hallucinations in ≤2 retries                      |
| `_deep_merge` for yaml + env layering                   | Shallow merge wiped sibling yaml keys when env provided partial nested override                     |
| `HISTORY_DB_PATH` anchored to project root              | Bare filename is CWD-dependent — breaks inside Docker where invocation dir may differ               |
| `.coderabbit.yaml` path instructions per module         | Security-critical paths (`validation/safety.py`, `llm/retry.py`) get explicit reviewer prompts      |
