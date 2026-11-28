# SQLWhisper — Decision Log

Format: ADR-lite. Append new entries at the bottom, never rewrite history. To reverse a decision, add a new entry that supersedes it.

Status values: **Accepted** · **Superseded by D-xx** · **Proposed**

## Index

| ID   | Decision                                                        | Status   |
| ---- | --------------------------------------------------------------- | -------- |
| D-01 | FastAPI backend + Streamlit UI                                  | Accepted |
| D-02 | Single Python package, `src/` layout, uv only                   | Accepted |
| D-03 | Sources: single CSV + Postgres URL                              | Accepted |
| D-04 | Postgres URLs only, no `sqlite://` URLs                         | Accepted |
| D-05 | CSV → SQLite file via pandas                                    | Accepted |
| D-06 | AST-based safety check, not a keyword blocklist                 | Accepted |
| D-07 | Read-only enforced at executor, independent of validator        | Accepted |
| D-08 | LIMIT enforced on the AST by the executor                       | Accepted |
| D-09 | Deterministic chart rules, not LLM chart JSON                   | Accepted |
| D-10 | Chart spec from API, Plotly built in UI                         | Accepted |
| D-11 | Env-only configuration, no `config.yaml`                        | Accepted |
| D-12 | Sync code everywhere                                            | Accepted |
| D-13 | `httpx` for Ollama, no SDK, no `requests`                       | Accepted |
| D-14 | Default model `qwen2.5:7b-instruct`, final pick by benchmark    | Superseded by D-39 |
| D-15 | Keyword table selector now, embeddings later                    | Accepted |
| D-16 | Follow-ups via client-sent last 3 Q/SQL pairs                   | Accepted |
| D-17 | Source registry in memory; credentials never persisted          | Accepted |
| D-18 | No seed database; tests build their own data                    | Accepted |
| D-19 | Single-stage Dockerfile, Ollama external                        | Accepted |
| D-20 | Feature branches off `master`, no `develop`                     | Accepted |
| D-21 | Sprint ID `X1`, tickets `X1-n`                                  | Accepted |
| D-22 | Retry budget: 2 retries (3 attempts)                            | Accepted |
| D-23 | Experiment (`chat-db-plotly`) retired                           | Accepted |
| D-24 | Flat docs, generated STRUCTURE.md, CLAUDE.md                    | Accepted |
| D-25 | Database run-time errors are retried like validator issues      | Accepted |
| D-26 | Pipeline returns `Answer`; API builds `QueryResult` + chart     | Accepted |
| D-27 | Read-only lives in the source engines                           | Accepted |
| D-28 | LLM call: temperature 0, reply cleaning in `extract_sql`        | Accepted |
| D-29 | Schema check is best effort, runs on the selected subset        | Accepted |
| D-30 | Mermaid diagrams, owned by ARCHITECTURE.md                      | Accepted |
| D-31 | Executor makes values JSON-safe, maps lost connection to 400    | Accepted |
| D-32 | `httpx2` as dev dependency for Starlette `TestClient`           | Accepted |
| D-33 | History is best effort; a failed log never changes the response | Accepted |
| D-34 | Internal errors log exception type and path only                | Accepted |
| D-35 | mypy skips missing stubs for `plotly`                           | Accepted |
| D-36 | Compose joins the `ollama-net` network                          | Accepted |
| D-37 | Streamlit telemetry and IP lookup off                           | Accepted |
| D-38 | Compose publishes ports on loopback only                        | Accepted |
| D-39 | Default model `qwen2.5:3b`, chosen by benchmark | Accepted |

---

## D-01 — FastAPI backend + Streamlit UI

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Pipeline lives behind a FastAPI API. Streamlit only renders.
**Why:** API is reusable (MCP wrapper, other UIs, scripts) and the pipeline is testable without Streamlit. Matches the original PRD.
**Cost:** Two processes and one extra hop. Acceptable locally.

## D-02 — Single package, `src/` layout, uv only

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** One repo, one package `sqlwhisper`. `main.py` and `requirements.txt` removed.
**Why:** KISS. Experiment code and original design merge into one codebase. `uv.lock` is the single dependency truth.

## D-03 — Sources: single CSV + Postgres URL

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** v0.2 supports one uploaded CSV or one Postgres URL.
**Why:** Covers "my own data" without multi-table join complexity. Multi-CSV is X2.

## D-04 — Postgres URLs only

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Reject `sqlite:///` and any other scheme on `/sources/url`.
**Why:** A SQLite URL lets API callers read any file the process can access. SQLite is reachable only via CSV upload.

## D-05 — CSV → SQLite file via pandas

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Uploaded CSV becomes a SQLite file under `DATA_DIR/uploads`, opened `mode=ro` for queries.
**Why:** One query path for both source types (SQLAlchemy). SQLite gives a real SQL dialect and a native read-only mode.
**Cost:** Dtype inference is pandas-quality. Dates kept as ISO text.

## D-06 — AST-based safety check

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** sqlglot parses; root must be SELECT/CTE/UNION; any write or DDL node anywhere → hard block; exactly one statement.
**Why:** A keyword blocklist rejects `update_date` and misses nested constructs. Structural checks are complete and testable.

## D-07 — Read-only at the executor

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** SQLite `mode=ro`; Postgres `default_transaction_read_only=on`. Applies to all sources.
**Why:** Independent of the validator. A bug in either layer alone cannot cause a write. No requirement for a read-only DB role.

## D-08 — LIMIT enforced on the AST

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Executor sets LIMIT to `min(existing, MAX_ROWS)` or adds it. Result carries `truncated`.
**Why:** Small models ignore prompt rules inconsistently. Only enforcement at execution is reliable.

## D-09 — Deterministic chart rules

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Chart type chosen from result shape by fixed rules.
**Why:** The experiment asked the model for chart JSON; a 3B model fails that often. Rules are testable and free. User override can come later.

## D-10 — Chart spec from API, Plotly in UI

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** API returns `{type, x, y, color?}`. UI builds the Plotly figure.
**Why:** Keeps Plotly out of the API image and responses small and JSON-clean.

## D-11 — Env-only configuration

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** `pydantic-settings` reads env / `.env`. No `config.yaml`.
**Why:** Sources are runtime inputs (upload/URL). The remaining knobs are few. Supersedes the `config.yaml` in PRD v0.1.

## D-12 — Sync code everywhere

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Plain `def` endpoints and functions. No async.
**Why:** FastAPI runs sync routes in a threadpool. Streamlit is sync. SQLAlchemy sync engine is simpler. Revisit only on measured concurrency pain.

## D-13 — `httpx` for Ollama

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Call Ollama's HTTP API directly with `httpx`. No `ollama` SDK, no `requests`.
**Why:** One HTTP library, mockable transport for tests, fewer dependencies. The experiment's `requests` use is replaced.

## D-14 — Default model

**Date:** 2026-11-09 · **Status:** Superseded by D-39
**Decision:** Start with `qwen2.5:7b-instruct`. Benchmark it against `qwen3:4b`, `qwen2.5:3b`, `llama3.2:3b` in X1-7 and record the winner here.
**Why:** `sqlcoder` and `deepseek-coder` from PRD v0.1 are not installed locally. Choose from what exists and measure.

## D-15 — Keyword selector now, embeddings later

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Inject all tables if ≤5, else keyword-rank and cap at 5.
**Why:** Zero extra dependency. `nomic-embed-text` is already installed, so the X3 upgrade is cheap behind the same function signature.

## D-16 — Follow-ups via client-sent context

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** UI sends the last 3 Q/SQL pairs in `/query`; server caps at 3.
**Why:** Stateless API, no session store. Enough for "now filter North".

## D-17 — In-memory registry, no persisted credentials

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** `source_id → DataSource` in memory. DB URL lives only inside the engine. Label is `host/db`. Uploads purged on startup.
**Why:** Privacy-first. Restart means re-upload; persistence is X3 and will store non-secret metadata only.

## D-18 — No seed database

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** No bundled sample DB. Tests build data in-test; benchmark CSV lives in `tests/fixtures/`.
**Why:** The experiment's seed ran `DROP TABLE` on start and used unseeded `random`, which is destructive and untestable.

## D-19 — Single-stage Dockerfile, Ollama external

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** One image for `api` and `ui`. No Ollama container in compose. `uv sync` without `--frozen`.
**Why:** Matches the existing Ollama setup (shared host/LAN instance). Single-stage keeps the build simple.

## D-20 — Branching

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Feature branches off `master`, PR, squash merge. No `develop`.
**Why:** Repo has only `master` and one solo developer. Supersedes the `develop` strategy in the old SPRINT_1.md.

## D-21 — Sprint naming

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** Sprints are `X1`, `X2`, …; tickets `X1-1`, `X1-2`, …
**Why:** Replaces `SW-n` from the old sprint doc. Roadmap versions map to sprints.

## D-22 — Retry budget

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** `MAX_RETRIES=2` (3 attempts). Safety violations never retry.
**Why:** Matches the success metric (≤2 retries to fix a hallucinated column). More retries cost latency on a local model for little gain.

## D-23 — Experiment retired

**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** `chat-db-plotly` is not merged as code. Carried over: Plotly charts, low temperature (0.1), JSON-free SQL output, chat-style UI.
**Why:** It was a working proof of concept, with hardcoded schema, a destructive DB init, no validation and a bare `except`. Rewrite is cheaper than retrofit.

## D-24 — Flat docs, generated STRUCTURE.md, CLAUDE.md

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** Keep a flat `docs/` (no `docs/sprints/Sn/`). `docs/STRUCTURE.md` is generated by `make tree` and never edited. `CLAUDE.md` at the repo root holds the engineering rules; its section 21 wins on conflict.
**Why:** One developer, one sprint at a time. Per-sprint folders add paths without adding information.

## D-25 — Database run-time errors are retried

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** `QueryFailed` (the database rejects a validated query) goes back to the model like a validator issue and ends as `ValidationFailed` (422) when retries run out. `UnsafeSQL` and `QueryTimeout` are never retried. Extends D-22.
**Why:** The validator cannot catch everything (type errors, unknown functions). The database message is a good correction signal.

## D-26 — Pipeline returns `Answer`; API builds `QueryResult`

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** `pipeline.answer` returns `Answer(result, attempts)`. The API adds `row_count` and the chart spec from `charts.pick_chart` to build `QueryResult`.
**Why:** Keeps presentation out of the pipeline. Chart rules stay unit-tested on their own.

## D-27 — Read-only lives in the source engines

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** Clarifies D-07. `CsvSource` opens SQLite `mode=ro`; `PostgresSource` sets `default_transaction_read_only=on`. The executor runs on `source.engine()` and enforces LIMIT and timeout only.
**Why:** One place per source, no dialect branching for read-only in the executor. Still independent of the validator.

## D-28 — LLM call settings

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** Supersedes the 0.1 temperature in D-23. `OllamaClient` calls `/api/chat` without streaming at temperature 0. `prompt.extract_sql` strips `<think>` blocks, code fences and trailing prose.
**Why:** Reproducible output for benchmarking. Qwen3-style models emit think blocks.

## D-29 — Schema check is best effort

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** The validator checks tables and columns against the selected subset using sqlglot `qualify`. If `qualify` fails for a reason other than an unknown name, the query passes to the database.
**Why:** sqlglot cannot analyse every construct, and the safety layers do not depend on this check. Database errors feed D-25.
**Cost:** Some hallucinated columns cost an extra database round trip. Revisit if the benchmark shows misses.

## D-30 — Mermaid diagrams, owned by ARCHITECTURE.md

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** Diagrams are Mermaid fences in `docs/ARCHITECTURE.md`. Other docs link to them. Tables, code contracts and the generated `STRUCTURE.md` stay as they are.
**Why:** GitHub renders Mermaid, no tooling needed, and one owner removes the duplicate pipeline picture the PRD had.
**Cost:** Raw text is harder to read in a terminal. A syntax error shows as a broken box and nothing in CI catches it, so preview on GitHub or in VS Code before the PR.

## D-31 — Executor output is JSON-safe; lost connection is a source error

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** `executor.plain_value` converts Decimal to int/float, NaN/inf to null and bytes to a placeholder before rows leave the executor. A psycopg `OperationalError` without a SQLSTATE becomes `SourceError` (400), not `QueryFailed`.
**Why:** JSON responses must not fail on database types. A dead connection is not something the model can fix, so it must not burn retries.
**Cost:** Decimal precision beyond float range is lost in the response.

## D-32 — `httpx2` as dev dependency

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** Add `httpx2` to the dev group. Runtime keeps `httpx` for the Ollama client (D-13).
**Why:** Starlette's `TestClient` deprecates `httpx` in favour of `httpx2` and warns on every test run. Tests use `TestClient`, so the dependency is real even though no file imports it.
**Cost:** Two HTTP libraries in the lockfile. Revisit when Starlette drops `httpx` support or the runtime client can move.

## D-33 — History is best effort

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** `history.log` runs after the answer is known. If it raises `sqlite3.Error`, the API logs a warning with the exception type only and returns the result as if nothing happened. On the failure path the original pipeline error still propagates; a history error never replaces it.
**Why:** The user's answer matters more than the audit trail. A full disk or locked file must not turn a good query into a 500.
**Cost:** A silent gap in history, visible only in logs.

## D-34 — Internal errors log type and path only

**Date:** 2026-11-21 · **Status:** Accepted
**Decision:** The 500 handler logs `unhandled <ExceptionType> on <path>` through `sqlwhisper.api`, with no message and no traceback. The client still gets `{"code": "internal_error", "message": "unexpected error"}`.
**Why:** Exception text can carry SQL, question text or driver details (privacy principle). The type and path are enough to find the code path.
**Cost:** Starlette re-raises after the handler, so uvicorn prints its own traceback in the server log. Left alone on purpose: it is local-only and needed for debugging.

## D-35 — mypy skips missing stubs for plotly

**Date:** 2026-11-22 · **Status:** Accepted
**Decision:** Add a `[[tool.mypy.overrides]]` with `ignore_missing_imports = true` for `plotly` and `plotly.*`. `strict` stays on everywhere else.
**Why:** Plotly ships no `py.typed` marker and no official stubs, so `mypy --strict` rejects the import. Only `ui.py` uses it (D-10). No new dependency.
**Cost:** Plotly objects are `Any` to mypy, so wrong plotly calls are not caught statically. `tests/test_ui.py` covers the figure helper.

## D-36 — Compose joins the ollama-hub network

**Date:** 2026-11-28 · **Status:** Accepted
**Decision:** `api` joins the external Docker network `ollama-net` and reaches Ollama at `${DOCKER_OLLAMA_URL:-http://ollama:11434}`. `DOCKER_OLLAMA_URL` is compose-only; `OLLAMA_URL` in `.env` stays the host-side value for `make api`. Compose still has no Ollama service (extends D-19).
**Why:** Ollama runs from the ollama-hub repo on the same machine, and its firewall limits published-port traffic to one client IP, so a container going through the host gateway may be dropped. The shared network avoids that path. `localhost` inside a container is the container itself, so the `.env` value cannot be reused.
**Cost:** `docker compose up` fails when the hub network is missing, so start the hub first. Ollama on another host needs `DOCKER_OLLAMA_URL` set to its URL and the `ollama-net` entries removed from `docker-compose.yml`.

## D-37 — Streamlit telemetry and IP lookup off

**Date:** 2026-11-28 · **Status:** Accepted
**Decision:** The UI starts with `--browser.gatherUsageStats false --browser.serverAddress localhost`, in `docker-compose.yml` and in `make ui`.
**Why:** The first container run logged "Collecting usage statistics" and printed an "External URL" with the host's public IP. Both reach the internet, which breaks "nothing leaves the machine". After the change neither line appears in the container logs.
**Cost:** The flags live in two places. Move them to `.streamlit/config.toml` if a third place needs them.

## D-38 — Compose publishes ports on loopback only

**Date:** 2026-11-28 · **Status:** Accepted
**Decision:** `docker-compose.yml` maps `127.0.0.1:8000` and `127.0.0.1:8501`, not all interfaces.
**Why:** The API has no auth (non-goal until X4) and accepts a Postgres URL from any caller. Docker publishes on all interfaces by default and bypasses host firewalls such as ufw, and the host has a public address. Found in review of the Docker PR.
**Cost:** Other machines cannot reach the UI until auth exists (X4). Use an SSH tunnel meanwhile.

## D-39 — Default model qwen2.5:3b

**Date:** 2026-11-28 · **Status:** Accepted
**Decision:** The default `OLLAMA_MODEL` is `qwen2.5:3b`. Resolves D-14.
**Why:** `make bench` (20 questions, fixed 96-row CSV in `tests/fixtures/`, temperature 0, one run, result values compared, not SQL text) gave first-attempt accuracy: `qwen2.5:3b` 16/20 (median 0.4 s), `qwen2.5:3b-gpu` 16/20 (0.3 s), `qwen2.5:7b-instruct` 16/20 (1.8 s), `llama3.2:3b` 12/20 (0.5 s), `qwen3:4b` 11/20 (27 s, and 6 of 20 hit the 60 s timeout on a 4 GB GPU). Three models tie on accuracy, so the fastest wins, as the rule was set before the runs.
**Cost:** 16/20 is exactly the PRD's 80% line, with no margin, and one run at n=20 cannot separate the tied models. Column order is strict, which cost `qwen2.5:3b-gpu` and `qwen2.5:3b` Q04 (values right, label last). The retry path ran once on the whole set (`llama3.2:3b`, Q07, still wrong), so "hallucinated column fixed in 2 retries" is not shown by the benchmark; `test_pipeline.py` covers the mechanism with a fake LLM. Q10 failed in every run (`qwen3:4b` by timeout) and Q08 and Q19 failed on three of five: the prompt carries schema only, no sample values (X2).

## Template

```md
## D-NN — Title
**Date:** YYYY-MM-DD · **Status:** Proposed | Accepted | Superseded by D-NN
**Decision:** one sentence.
**Why:** one to three sentences.
**Cost:** what we give up (optional).
```
