# Sprint 1 (X1) — TODO

**Goal:** `docker compose up` → open `localhost:8501` → upload a CSV (or paste a Postgres URL) → ask in English → validated read-only SQL + table + chart.

**Branching:** feature branch per ticket, off `master`, PR, squash merge. Branch names below.
**Per-ticket loop:** write failing tests → make green with the least code → refactor → `make check` → PR.

Order is strict: each ticket depends on the one before.

---

## X1-1 — Scaffold + settings

**Branch:** `feature/x1-1-scaffold`

Tests first

- [x] Settings load defaults when env is empty
- [x] Env vars override defaults (`OLLAMA_MODEL`, `MAX_ROWS`, …)
- [x] Invalid value (`MAX_ROWS=abc`) raises a validation error

Implement

- [x] `git rm main.py requirements.txt`
- [x] `pyproject.toml`: name `sqlwhisper`, `uv_build` backend, deps from PRD, dev group (`pytest`, `ruff`, `mypy`)
- [x] `src/sqlwhisper/` package, `settings.py` (pydantic-settings, env only), `errors.py`, `models.py` stubs
- [x] `.env.example` with every var documented
- [x] `Makefile`: `check` (ruff, mypy --strict, pytest), `test`, `tags`, `smoke` (`api` in X1-5, `ui` in X1-6)
- [x] `ruff` + `mypy` strict config in `pyproject.toml`
- [x] README stub: install + run

**Done when:** `uv sync && make check` is green on a clean clone.

---

## X1-2 — Sources + schema + selector

**Branch:** `feature/x1-2-sources-schema`

Tests first

- [x] CSV: loads, table name from filename, headers normalised (`"Order Date"` → `order_date`), duplicate headers deduped
- [x] CSV: over `MAX_UPLOAD_MB` rejected, non-CSV rejected, empty file rejected
- [x] CSV source engine is read-only (a write raises)
- [x] Postgres: label is `host/db` and never contains the password
- [x] Postgres: non-`postgresql://` URL (incl. `sqlite:///`) rejected
- [x] Registry: add, get, unknown id raises `SourceError`
- [x] Schema: tables, columns, types, PK/FK introspected from a built-in-test SQLite DB
- [x] Selector: ≤5 tables returns all; >5 ranks by keyword hits on table and column names, caps at 5

Implement

- [x] `sources/base.py` (`DataSource` protocol), `csv.py`, `postgres.py`, `registry.py`
- [x] `schema.py`: `introspect()`, `select_tables()`
- [x] Purge `DATA_DIR/uploads` on startup helper

**Done when:** all tests green, no network needed (Postgres tests use URL parsing only).

---

## X1-3 — Validator + executor

**Branch:** `feature/x1-3-validator-executor`

Tests first (validator)

- [x] Valid SELECT, CTE, UNION pass
- [x] Syntax error → `SyntaxIssue` with readable message
- [x] Unknown table / unknown column → `SchemaIssue` naming the closest valid name
- [x] `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT` → `UnsafeSQL`
- [x] Write node hidden in a CTE or subquery → `UnsafeSQL`
- [x] Two statements (`SELECT 1; DROP TABLE x`) → `UnsafeSQL`
- [x] Column named `update_date` passes (no keyword false positive)
- [x] Dialect respected (sqlite vs postgres quirks, one case each)

Tests first (executor)

- [x] LIMIT added when missing; lowered when above `MAX_ROWS`; kept when lower
- [x] `truncated` flag set when the row cap was hit
- [x] Write attempt on the read-only engine fails even when the validator is bypassed
- [x] Timeout raises `QueryTimeout`

Implement

- [x] `validator.py` (pure functions), `executor.py`, `ResultSet` model

**Done when:** validator blocks 100% of non-SELECT cases in the suite; no LLM involved yet.

---

## X1-4 — LLM client + prompt + pipeline

**Branch:** `feature/x1-4-pipeline`

Tests first

- [x] `OllamaClient`: success, connection refused → `LLMUnavailable`, timeout → `LLMUnavailable` (httpx mock transport)
- [x] Prompt contains dialect, selected tables only, rules, last 3 context pairs (older ones dropped)
- [x] Prompt never contains row data
- [x] SQL extraction strips code fences and prose
- [x] Pipeline with `FakeLLM`: valid on first try → 1 attempt
- [x] Pipeline: bad column then fixed → 2 attempts, correction prompt includes error text
- [x] Pipeline: still invalid after `MAX_RETRIES` → `ValidationFailed` with last SQL
- [x] Pipeline: `UnsafeSQL` → stops immediately, no retry

Implement

- [x] `llm.py`, `prompt.py`, `pipeline.py`
- [x] Opt-in smoke test `pytest -m ollama` (one real question)

**Done when:** pipeline tests green with `FakeLLM`; smoke test passes against local Ollama (`make tags` shows the model).

---

## X1-5 — API + history

**Branch:** `feature/x1-5-api-history`

Tests first (`TestClient`, `FakeLLM`)

- [x] `GET /health`: Ollama up/down, model present/missing
- [x] `POST /sources/csv` happy path returns `source_id` + tables
- [x] `POST /sources/url` bad URL → 400
- [x] `GET /sources/{id}/schema`
- [x] `POST /query` happy path returns the `QueryResult` shape (incl. `chart`)
- [x] Each error maps to its HTTP code and body shape (400, 422 ×2, 502, 504)
- [x] History: logged on success and failure, capped at 20 on read, no password anywhere in the DB or response

Implement

- [x] `api.py` (wiring, routes, exception handlers), `history.py`
- [x] `Makefile`: `api` target
- [x] Call `purge_uploads` on startup; build `QueryResult` from `Answer` + `row_count` + chart ([D-26](DECISION.md))
- [x] Chart picker detects date-like columns itself (the schema does not flag them)
- [x] `charts.py` here, because `/query` returns the chart spec. Tests first, one case per rule row in the architecture doc

**Done when:** `make api`, then `curl` with a CSV and a question returns SQL + rows.

---

## X1-6 — Streamlit UI

**Branch:** `feature/x1-6-ui`

Tests first

- [ ] Pure helper: chart spec → Plotly figure (bar, line, scatter, none)
- [ ] Pure helper: build `context[]` from the last 3 chat turns
- [ ] Pure helper: map API error body → user-facing message

Implement

- [ ] `Makefile`: `ui` target
- [ ] Sidebar: CSV uploader, DB URL input (password-masked), Ollama status, schema explorer, last-20 history (click to re-run)
- [ ] Main: chat input, collapsible SQL, `st.dataframe`, chart, CSV download
- [ ] Inline error states: Ollama down, bad source, validation exhausted (shows last SQL), unsafe, timeout
- [ ] Spinner + elapsed time

**Done when:** manual run-through of 5 questions on a sample CSV, including one follow-up ("now only North").

---

## X1-7 — Docker + benchmark + README

**Branch:** `feature/x1-7-docker-bench`

- [ ] Single-stage `Dockerfile` (uv, non-root), shared by both services
- [ ] `docker-compose.yml`: `api`, `ui`, `./data` volume, `OLLAMA_URL` from env, no Ollama service
- [ ] `uv sync` in the Dockerfile without `--frozen`
- [ ] Benchmark: fixed CSV (committed under `tests/fixtures/`), 20 questions with expected result checks, run per model: `qwen2.5:7b-instruct`, `qwen3:4b`, `qwen2.5:3b`, `llama3.2:3b`
- [ ] Pick default model from the results, record it in `DECISION.md`
- [ ] README: quick start, env table, screenshots, benchmark table
- [ ] Cold-start check: `docker compose up` → UI usable in <60 s

**Done when:** a fresh clone runs end to end with only `.env` filled in.

---

## X1-5b — API hardening (follow-ups from the X1-5 review)

Each item: own branch off `master`, failing test first, `make check`, PR, squash merge.

- [x] `pick_chart` no longer crashes on a numeric plus an all-null column (`feature/x1-5-chart-guard`)
- [x] `internal_error` handler logs exception type and path, never the message (`feature/x1-5-log-internal-errors`)
- [x] `history.log` failure is best effort: warn with the exception type only, return the result, never replace the pipeline error ([D-33](DECISION.md)) (`feature/x1-5-history-best-effort`)
- [x] `api.query` logs `ok=False` only for domain errors (`SourceError`, `UnsafeSQL`, `ValidationFailed`, `LLMUnavailable`, `QueryTimeout`, `SQLAlchemyError`), not for unexpected exceptions
- [ ] Test: a stray `SQLAlchemyError` returns 400 `bad_source` with the fixed message and no driver text
- [ ] Manual run-through of the X1-5 curl check was done on 2026-11-21 with `data/sales.csv`: upload, schema, bar, line, follow-up, blocked DELETE, history. Add a short curl example to the README

## Definition of done (sprint)

- [ ] All seven PRs merged
- [ ] `make check` green: `ruff`, `mypy --strict`, `pytest`
- [ ] ≥80% first-attempt accuracy on the 20-question benchmark
- [ ] 100% of non-SELECT cases blocked pre-execution
- [ ] Hallucinated column fixed within 2 retries on the benchmark
- [ ] No unhandled exception on: Ollama down, bad SQL, bad URL, oversized upload, timeout
- [ ] No credential in logs, history or responses (grep test)
- [ ] Docs match the code (`PRD.md`, `ARCHITECTURE.md`, `DECISION.md`)

## Out of scope (→ ROADMAP X2+)

Multiple CSVs, MySQL, Excel, embeddings, explain-result, suggest-queries, auth, MCP, cloud LLM.

## Parking lot

- `CsvSource` never disposes its engine; matters once sources can be removed.
- Validation runs against the selected table subset, so a model that uses a table outside it gets a retry. Intended? Check in the benchmark.
- On a 500, uvicorn still prints its own traceback, message included. Kept on purpose for local debugging.
- First query after a cold start can hit `OLLAMA_TIMEOUT_S=60` (`llm_unavailable`, ReadTimeout). Check in the benchmark.
