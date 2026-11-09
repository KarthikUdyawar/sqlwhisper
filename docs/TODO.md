# Sprint 1 (X1) — TODO

**Goal:** `docker compose up` → open `localhost:8501` → upload a CSV (or paste a Postgres URL) → ask in English → validated read-only SQL + table + chart.

**Branching:** feature branch per ticket, off `master`, PR, squash merge. Branch names below.
**Per-ticket loop:** write failing tests → make green with the least code → refactor → `make check` → PR.

Order is strict: each ticket depends on the one before.

---

## X1-1 — Scaffold + settings

**Branch:** `feature/x1-1-scaffold`

Tests first

- [ ] Settings load defaults when env is empty
- [ ] Env vars override defaults (`OLLAMA_MODEL`, `MAX_ROWS`, …)
- [ ] Invalid value (`MAX_ROWS=abc`) raises a validation error

Implement

- [ ] `git rm main.py requirements.txt`
- [ ] `pyproject.toml`: name `sqlwhisper`, `uv_build` backend, deps from PRD, dev group (`pytest`, `ruff`, `mypy`)
- [ ] `src/sqlwhisper/` package, `settings.py` (pydantic-settings, env only), `errors.py`, `models.py` stubs
- [ ] `.env.example` with every var documented
- [ ] `Makefile`: `check` (ruff, mypy --strict, pytest), `api`, `ui`, `test`, `tags`
- [ ] `ruff` + `mypy` strict config in `pyproject.toml`
- [ ] README stub: install + run

**Done when:** `uv sync && make check` is green on a clean clone.

---

## X1-2 — Sources + schema + selector

**Branch:** `feature/x1-2-sources-schema`

Tests first

- [ ] CSV: loads, table name from filename, headers normalised (`"Order Date"` → `order_date`), duplicate headers deduped
- [ ] CSV: over `MAX_UPLOAD_MB` rejected, non-CSV rejected, empty file rejected
- [ ] CSV source engine is read-only (a write raises)
- [ ] Postgres: label is `host/db` and never contains the password
- [ ] Postgres: non-`postgresql://` URL (incl. `sqlite:///`) rejected
- [ ] Registry: add, get, unknown id raises `SourceError`
- [ ] Schema: tables, columns, types, PK/FK introspected from a built-in-test SQLite DB
- [ ] Selector: ≤5 tables returns all; >5 ranks by keyword hits on table and column names, caps at 5

Implement

- [ ] `sources/base.py` (`DataSource` protocol), `csv.py`, `postgres.py`, `registry.py`
- [ ] `schema.py`: `introspect()`, `select_tables()`
- [ ] Purge `DATA_DIR/uploads` on startup helper

**Done when:** all tests green, no network needed (Postgres tests use URL parsing only).

---

## X1-3 — Validator + executor

**Branch:** `feature/x1-3-validator-executor`

Tests first (validator)

- [ ] Valid SELECT, CTE, UNION pass
- [ ] Syntax error → `SyntaxIssue` with readable message
- [ ] Unknown table / unknown column → `SchemaIssue` naming the closest valid name
- [ ] `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT` → `UnsafeSQL`
- [ ] Write node hidden in a CTE or subquery → `UnsafeSQL`
- [ ] Two statements (`SELECT 1; DROP TABLE x`) → `UnsafeSQL`
- [ ] Column named `update_date` passes (no keyword false positive)
- [ ] Dialect respected (sqlite vs postgres quirks, one case each)

Tests first (executor)

- [ ] LIMIT added when missing; lowered when above `MAX_ROWS`; kept when lower
- [ ] `truncated` flag set when the row cap was hit
- [ ] Write attempt on the read-only engine fails even when the validator is bypassed
- [ ] Timeout raises `QueryTimeout`

Implement

- [ ] `validator.py` (pure functions), `executor.py`, `ResultSet` model

**Done when:** validator blocks 100% of non-SELECT cases in the suite; no LLM involved yet.

---

## X1-4 — LLM client + prompt + pipeline

**Branch:** `feature/x1-4-pipeline`

Tests first

- [ ] `OllamaClient`: success, connection refused → `LLMUnavailable`, timeout → `LLMUnavailable` (httpx mock transport)
- [ ] Prompt contains dialect, selected tables only, rules, last 3 context pairs (older ones dropped)
- [ ] Prompt never contains row data
- [ ] SQL extraction strips code fences and prose
- [ ] Pipeline with `FakeLLM`: valid on first try → 1 attempt
- [ ] Pipeline: bad column then fixed → 2 attempts, correction prompt includes error text
- [ ] Pipeline: still invalid after `MAX_RETRIES` → `ValidationFailed` with last SQL
- [ ] Pipeline: `UnsafeSQL` → stops immediately, no retry

Implement

- [ ] `llm.py`, `prompt.py`, `pipeline.py`
- [ ] Opt-in smoke test `pytest -m ollama` (one real question)

**Done when:** pipeline tests green with `FakeLLM`; smoke test passes against local Ollama (`make tags` shows the model).

---

## X1-5 — API + history

**Branch:** `feature/x1-5-api-history`

Tests first (`TestClient`, `FakeLLM`)

- [ ] `GET /health`: Ollama up/down, model present/missing
- [ ] `POST /sources/csv` happy path returns `source_id` + tables
- [ ] `POST /sources/url` bad URL → 400
- [ ] `GET /sources/{id}/schema`
- [ ] `POST /query` happy path returns the `QueryResult` shape (incl. `chart`)
- [ ] Each error maps to its HTTP code and body shape (400, 422 ×2, 502, 504)
- [ ] History: logged on success and failure, capped at 20 on read, no password anywhere in the DB or response

Implement

- [ ] `api.py` (wiring, routes, exception handlers), `history.py`
- [ ] `charts.py` here, because `/query` returns the chart spec. Tests first, one case per rule row in the architecture doc

**Done when:** `make api`, then `curl` with a CSV and a question returns SQL + rows.

---

## X1-6 — Streamlit UI

**Branch:** `feature/x1-6-ui`

Tests first

- [ ] Pure helper: chart spec → Plotly figure (bar, line, scatter, none)
- [ ] Pure helper: build `context[]` from the last 3 chat turns
- [ ] Pure helper: map API error body → user-facing message

Implement

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

_(add items here instead of widening scope)_
