# SQLWhisper — Decision Log

Format: ADR-lite. Append new entries at the bottom, never rewrite history. To reverse a decision, add a new entry that supersedes it.

Status values: **Accepted** · **Superseded by D-xx** · **Proposed**

## Index

| ID   | Decision                                                     | Status   |
| ---- | ------------------------------------------------------------ | -------- |
| D-01 | FastAPI backend + Streamlit UI                               | Accepted |
| D-02 | Single Python package, `src/` layout, uv only                | Accepted |
| D-03 | Sources: single CSV + Postgres URL                           | Accepted |
| D-04 | Postgres URLs only, no `sqlite://` URLs                      | Accepted |
| D-05 | CSV → SQLite file via pandas                                 | Accepted |
| D-06 | AST-based safety check, not a keyword blocklist              | Accepted |
| D-07 | Read-only enforced at executor, independent of validator     | Accepted |
| D-08 | LIMIT enforced on the AST by the executor                    | Accepted |
| D-09 | Deterministic chart rules, not LLM chart JSON                | Accepted |
| D-10 | Chart spec from API, Plotly built in UI                      | Accepted |
| D-11 | Env-only configuration, no `config.yaml`                     | Accepted |
| D-12 | Sync code everywhere                                         | Accepted |
| D-13 | `httpx` for Ollama, no SDK, no `requests`                    | Accepted |
| D-14 | Default model `qwen2.5:7b-instruct`, final pick by benchmark | Proposed |
| D-15 | Keyword table selector now, embeddings later                 | Accepted |
| D-16 | Follow-ups via client-sent last 3 Q/SQL pairs                | Accepted |
| D-17 | Source registry in memory; credentials never persisted       | Accepted |
| D-18 | No seed database; tests build their own data                 | Accepted |
| D-19 | Single-stage Dockerfile, Ollama external                     | Accepted |
| D-20 | Feature branches off `master`, no `develop`                  | Accepted |
| D-21 | Sprint ID `X1`, tickets `X1-n`                               | Accepted |
| D-22 | Retry budget: 2 retries (3 attempts)                         | Accepted |
| D-23 | Experiment (`chat-db-plotly`) retired                        | Accepted |
| D-24 | Flat docs, generated STRUCTURE.md, CLAUDE.md                 | Accepted |
| D-25 | Database run-time errors are retried like validator issues   | Accepted |
| D-26 | Pipeline returns `Answer`; API builds `QueryResult` + chart  | Accepted |
| D-27 | Read-only lives in the source engines                        | Accepted |
| D-28 | LLM call: temperature 0, reply cleaning in `extract_sql`     | Accepted |
| D-29 | Schema check is best effort, runs on the selected subset     | Accepted |
| D-30 | Mermaid diagrams, owned by ARCHITECTURE.md                 | Accepted |

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

**Date:** 2026-11-09 · **Status:** Proposed
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

## Template

```md
## D-NN — Title
**Date:** YYYY-MM-DD · **Status:** Proposed | Accepted | Superseded by D-NN
**Decision:** one sentence.
**Why:** one to three sentences.
**Cost:** what we give up (optional).
```
