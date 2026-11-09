# SQLWhisper — Architecture

Version 0.2. Companion to `PRD.md`. Decisions and reasons live in `DECISION.md`.

---

## 1. System view

```bash
┌────────────┐   HTTP/JSON    ┌────────────────────────────────────┐
│ Streamlit  │ ─────────────▶ │ FastAPI (api.py)                   │
│  ui.py     │ ◀───────────── │   routes → pipeline → executor     │
└────────────┘                └──────┬───────────────┬─────────────┘
                                     │               │
                              ┌──────▼─────┐   ┌─────▼──────────────┐
                              │ Ollama     │   │ Data sources       │
                              │ (external) │   │ CSV→SQLite │ PG URL│
                              └────────────┘   └────────────────────┘
```

Two processes (`api`, `ui`), one image, one Python package. Ollama is external (host, LAN, or another compose project).

## 2. Layering and dependency rule

Imports point downward only. A lower layer never imports a higher one.

```bash
ui.py ───────────────▶ models        (talks to API over HTTP only)
api.py ──────────────▶ pipeline, sources.registry, history, models
pipeline.py ─────────▶ validator, prompt, executor, charts, protocols
validator / prompt / executor / charts / schema   (pure logic)
sources.* / llm.OllamaClient                      (adapters, implement protocols)
protocols, models, settings                       (leaf layer)
```

`pipeline` knows protocols, never `OllamaClient`, `CsvSource` or `PostgresSource`. Wiring happens once, in `api.py`.

## 3. Modules

| Module                | Responsibility                                                 | State?       |
| --------------------- | -------------------------------------------------------------- | ------------ |
| `settings.py`         | Env → typed settings                                           | none         |
| `models.py`           | Pydantic request/response models, `Schema`, `ResultSet`        | none         |
| `errors.py`           | Domain exceptions (see §7)                                     | none         |
| `sources/base.py`     | `DataSource` protocol                                          | none         |
| `sources/csv.py`      | CSV → SQLite file, normalise columns, read-only engine         | file on disk |
| `sources/postgres.py` | Postgres engine, read-only transaction, label without password | engine       |
| `sources/registry.py` | `source_id → DataSource`                                       | in memory    |
| `schema.py`           | Introspect, keyword table selector                             | none         |
| `llm.py`              | `LLMClient` protocol, `OllamaClient` (httpx)                   | none         |
| `prompt.py`           | Build system prompt + correction prompt                        | none         |
| `validator.py`        | sqlglot parse → safety → schema check                          | none         |
| `executor.py`         | Enforce LIMIT on AST, run read-only, timeout                   | none         |
| `charts.py`           | Result shape → chart spec                                      | none         |
| `pipeline.py`         | generate → validate → retry → execute → chart                  | none         |
| `history.py`          | SQLite log of queries                                          | file on disk |
| `api.py`              | FastAPI routes, error mapping, wiring                          | app state    |
| `ui.py`               | Streamlit rendering, Plotly figure from chart spec             | session      |

KISS rule: plain functions where there is no state. Classes only for adapters and anything holding state.

## 4. Contracts

```python
class LLMClient(Protocol):
    def complete(self, system: str, messages: list[Message]) -> str: ...

class DataSource(Protocol):
    id: str
    label: str                      # safe to display and log
    dialect: Literal["sqlite", "postgres"]
    def engine(self) -> Engine: ...  # read-only engine
    def schema(self) -> Schema: ...  # cached

def validate(sql: str, schema: Schema, dialect: str) -> ValidatedSQL: ...
    # raises SyntaxIssue | UnsafeSQL | SchemaIssue

def run(source: DataSource, sql: ValidatedSQL, *, max_rows: int, timeout_s: int) -> ResultSet: ...

def pick_chart(result: ResultSet) -> ChartSpec | None: ...

def answer(question: str, context: list[QA], source: DataSource,
           llm: LLMClient, cfg: PipelineConfig) -> QueryResult: ...
``

All sync. FastAPI endpoints are plain `def`, so they run in a threadpool. No async machinery.

## 5. Request flow: `POST /query`

```

1. api: look up source_id → DataSource           (400 if unknown)
2. pipeline: schema = source.schema()
3. schema.select_tables(question, schema, k=5)
4. prompt.build(dialect, subset, question, context[-3:])
5. loop attempt = 1..(1 + MAX_RETRIES):
     sql = llm.complete(...)                      (502 if Ollama down)
     try validate(sql, schema, dialect)
       UnsafeSQL   → stop, no retry               (422 unsafe_sql)
       Syntax/Schema issue → prompt.correction(sql, err); continue
     break
   exhausted → 422 validation_failed + last_sql
6. executor.run(source, validated, ...)           (504 on timeout)
7. charts.pick_chart(result)
8. history.log(...)                               (never stores credentials)
9. return QueryResult
``

## 6. Safety model (defense in depth)

| Layer | Mechanism                                                                     | Protects against           |
| ----- | ----------------------------------------------------------------------------- | -------------------------- |
| 1     | Prompt rules: single SELECT, exact columns                                    | Most bad output (soft)     |
| 2     | Validator: AST root must be SELECT/CTE/UNION; write/DDL node anywhere → block | Model emits writes         |
| 3     | Read-only connection: SQLite `mode=ro`, PG `default_transaction_read_only=on`        | Validator bug              |
| 4     | LIMIT enforced on AST (default 500)                                           | Huge result sets           |
| 5     | Statement timeout (default 15 s)                                              | Runaway queries            |
| 6     | Schema-only prompts: no row data ever sent to the LLM                         | Prompt injection via cells |

Layers 2 and 3 are independent: either one alone stops a write.

## 7. Errors → HTTP

| Exception          | HTTP | Code                | Retry?                  |
| ------------------ | ---- | ------------------- | ----------------------- |
| `SourceError`      | 400  | `bad_source`        | no                      |
| `UnsafeSQL`        | 422  | `unsafe_sql`        | no                      |
| `ValidationFailed` | 422  | `validation_failed` | after retries exhausted |
| `LLMUnavailable`   | 502  | `llm_unavailable`   | no                      |
| `QueryTimeout`     | 504  | `query_timeout`     | no                      |

Body shape: `{"code": "...", "message": "...", "last_sql": "..."?}`. No stack traces to the client.

## 8. Data and storage

| What            | Where                             | Lifetime                         |
| --------------- | --------------------------------- | -------------------------------- |
| Uploaded CSV    | `DATA_DIR/uploads/{source_id}.db` | Purged on API startup            |
| Source registry | In memory                         | Process (restart → re-upload)    |
| Postgres URL    | In memory, inside the engine only | Process. Never logged or stored  |
| History         | `DATA_DIR/history.db` (SQLite)    | Persistent, last 20 read via API |
| Chat/session    | Streamlit `session_state`         | Browser session                  |

## 9. CSV ingestion rules

- One file, ≤ `MAX_UPLOAD_MB`.
- Table name = filename stem, `snake_case`.
- Columns normalised to `snake_case`, deduplicated with numeric suffix.
- pandas dtype inference → SQLite types. Date-like columns kept as ISO text and flagged in schema for the chart picker.

## 10. Chart picker rules

| Result shape                | Chart   |
| --------------------------- | ------- |
| 1 row, or no numeric column | none    |
| date-like column + numeric  | line    |
| categorical + numeric       | bar     |
| two numeric columns         | scatter |
| otherwise                   | none    |

API returns a `ChartSpec {type, x, y, color?}`. The UI turns it into a Plotly figure. The API has no Plotly dependency.

## 11. Deployment

```bash
docker-compose.yml
  api: uv run uvicorn sqlwhisper.api:app --host 0.0.0.0 --port 8000
  ui:  uv run streamlit run src/sqlwhisper/ui.py   (API_URL=http://api:8000)
  ollama: external → OLLAMA_URL (e.g. host.docker.internal:11434 or LAN IP)
```

- One single-stage Dockerfile, shared by both services, different `command`.
- `data/` mounted as a volume.
- Non-root user.
- `uv sync` without `--frozen` unless the lockfile is confirmed present and current.

## 12. Testing strategy

| Level          | Scope                                       | Fakes                          |
| -------------- | ------------------------------------------- | ------------------------------ |
| Unit           | validator, schema, prompt, charts, executor | tiny seeded in-test SQLite     |
| Unit           | pipeline                                    | `FakeLLM` returns scripted SQL |
| Integration    | API via `TestClient`                        | `FakeLLM`, real SQLite         |
| Smoke (opt-in) | Real Ollama, 1 question                     | none (`pytest -m ollama`)      |
| Benchmark      | Fixed CSV + 20 questions, per model         | none (`make bench`)            |

Test data is built inside tests (no checked-in seed DB, no `random` without a seed).

## 13. Extension points

| Change                   | Touch only                                              |
| ------------------------ | ------------------------------------------------------- |
| New source (MySQL, xlsx) | New `sources/*.py` + one dialect entry + registry route |
| New LLM backend          | New class implementing `LLMClient`, wired in `api.py`   |
| New chart type           | `charts.py` rule + UI mapping                           |
| Embedding selector       | New function with the `select_tables` signature         |
| Auth                     | FastAPI dependency on routes, no pipeline change        |
