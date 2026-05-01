# SQLWhisper — Product Requirements Document

**Version:** 0.1.0  
**Timeline:** 7 days (solo dev)  
**Stack:** FastAPI · Ollama · SQLAlchemy · sqlglot · Streamlit · Docker  
**Model:** `sqlcoder:7b` (fallback: `deepseek-coder:6.7b`)

---

## Problem

Non-technical users can't query their own data. Technical users waste time writing boilerplate SQL for simple lookups. Cloud NL→SQL tools (e.g. Outerbase, AI2SQL) require sending schema + data to external APIs — a privacy risk for internal DBs.

SQLWhisper solves this locally: plain English in, SQL + results out, zero data leaving the machine.

---

## Goal

Ship a working, Docker-deployable NL→SQL tool in 7 days with:
- Schema-aware SQL generation via local Ollama
- AST-level SQL validation with auto-retry
- Read-only safety enforcement
- Streamlit UI with query box, SQL preview, result table, CSV export

---

## Non-Goals (v0.1)

- MCP server integration (deferred)
- Auth / multi-user support
- Write query support (INSERT / UPDATE / DELETE)
- Cloud LLM fallback
- Embedding-based table retrieval (use keyword matching only)

---

## Users

| User           | Need                                              |
| -------------- | ------------------------------------------------- |
| Solo developer | Query local dev DB without writing SQL            |
| Data analyst   | Quick ad-hoc queries without opening a SQL client |
| Indie hacker   | Ship internal analytics dashboard fast            |

---

## Architecture

```
User (Streamlit)
    │  plain English question
    ▼
Query Parser          — strip, normalise input
    │
    ├── Schema Layer  — SQLAlchemy introspect → relevant tables (keyword match)
    │
    ▼
Prompt Builder        — inject schema subset + dialect + rules
    │
    ▼
Ollama LLM            — generate raw SQL
    │
    ▼
SQL Validator         — sqlglot parse → column/table check → safety check
    │  fail → retry with error message (max 3x)
    ▼
Query Executor        — read-only SQLAlchemy session
    │
    ▼
Result Renderer       — markdown table + SQL preview + CSV export
```

---

## Features

### F1 — Schema introspection
- On startup, inspect all tables via `sqlalchemy.inspect()`
- Cache: `{table: {columns: [...], pk, fk, row_count}}`
- Keyword match: extract nouns from question → find relevant tables
- Max 5 tables injected into prompt (context budget)

### F2 — Prompt builder
```
You are an expert {dialect} SQL engineer.

Schema:
{schema_subset}

Rules:
- Return ONLY valid SQL, no explanation, no markdown fences
- Never use DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER
- Always alias tables
- LIMIT 500 rows unless user specifies otherwise
- Use exact column names from schema above

Question: {question}

SQL:
```

### F3 — SQL validator
**Stage 1 — Syntax parse** (`sqlglot`)
- Parse with target dialect (postgres / sqlite / mysql)
- On parse error → feed error back to Ollama with correction prompt

**Stage 2 — Schema check**
- Extract all table + column refs from AST
- Diff against cached schema
- On unknown column → correction prompt: `"Column 'revenue' not found. Use: 'total_amount'"` 

**Stage 3 — Safety check**
- Block: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `GRANT`, `EXEC`
- Hard block — no retry, surface error immediately

**Retry loop:** max 3 attempts → on 3rd failure surface error to user with last SQL attempt shown.

### F4 — Query executor
- Separate read-only SQLAlchemy session (`execution_options(no_parameters=True)`)
- Hard `LIMIT 500` appended if missing
- Return: `List[Dict]` + column names + execution time ms

### F5 — Streamlit UI
- Text area: plain English question
- DB selector dropdown (from `config.yaml`)
- "Run" button
- Collapsible SQL preview (syntax highlighted via `st.code`)
- Result table (`st.dataframe`)
- CSV export button
- Query history (last 20, stored in SQLite)
- "Explain this result" button → sends SQL + result back to Ollama for NL summary

---

## Config

```yaml
# config.yaml
ollama:
  base_url: http://localhost:11434
  model: sqlcoder:7b
  timeout_seconds: 30

databases:
  default:
    url: postgresql://user:pass@localhost/mydb
    dialect: postgresql
  local:
    url: sqlite:///./dev.db
    dialect: sqlite

app:
  max_rows: 500
  max_retries: 3
  max_tables_in_prompt: 5
```

All secrets via `.env`, loaded by `pydantic-settings`.

---

## Day-by-Day Plan

### Day 1 — Core engine (CLI only)
- [ ] `uv init sqlwhisper`, project scaffold
- [ ] `DatabaseConnector` class: connect + `inspect_schema()` → cache
- [ ] `KeywordTableSelector`: extract nouns → match tables
- [ ] `PromptBuilder`: assemble prompt string
- [ ] `OllamaClient`: call `/api/generate`, stream response, extract SQL
- [ ] Manual test: 10 questions against a local SQLite DB

**Done when:** `python -m sqlwhisper.cli "show top 5 customers"` returns valid SQL + results.

### Day 2 — Validation loop
- [ ] `SQLValidator.parse()`: `sqlglot` AST parse, catch syntax errors
- [ ] `SQLValidator.check_schema()`: extract refs, diff against cache
- [ ] `SQLValidator.check_safety()`: keyword blocklist
- [ ] `RetryOrchestrator`: loop max 3x, build correction prompts
- [ ] Unit tests: 10 cases (valid SQL, bad column, bad syntax, blocked keyword)

**Done when:** validator catches hallucinated columns and corrects via retry.

### Day 3 — Query executor + result layer
- [ ] `QueryExecutor`: read-only session, auto-LIMIT, return `ResultSet`
- [ ] `ResultFormatter`: `List[Dict]` → markdown table string
- [ ] Execution time tracking
- [ ] Error surfacing: friendly messages for DB connection failures
- [ ] Integration test: full pipeline end-to-end on 20 questions

**Done when:** full pipeline CLI test passes with <3s avg latency on sqlcoder:7b.

### Day 4 — Streamlit UI
- [ ] App scaffold: sidebar config, main query area
- [ ] DB selector from `config.yaml`
- [ ] Query input + Run button
- [ ] SQL preview (`st.code`, collapsible)
- [ ] Result table (`st.dataframe`, paginated)
- [ ] CSV export
- [ ] Loading spinner + elapsed time display

**Done when:** UI runs locally, submits question, shows SQL + results.

### Day 5 — History + explain + polish
- [ ] SQLite query history log (question, SQL, rows returned, timestamp)
- [ ] History sidebar (last 20, click to re-run)
- [ ] "Explain this result" → Ollama NL summary
- [ ] "Suggest queries" → Ollama generates 5 starter questions from schema
- [ ] Error states: no Ollama, no DB, validation failure — all handled gracefully

**Done when:** full UI flow works including history and explain.

### Day 6 — Docker + multi-DB
- [ ] `Dockerfile` + `docker-compose.yml` (app + optional postgres)
- [ ] Multi-DB config tested (postgres + sqlite simultaneously)
- [ ] `.env.example`
- [ ] Health check endpoint (`/health`)
- [ ] Model benchmark: sqlcoder:7b vs deepseek-coder:6.7b on 20 queries

**Done when:** `docker compose up` → UI live at `localhost:8501`.

### Day 7 — Docs + demo
- [ ] `README.md`: install, config, usage, screenshots
- [ ] `PROMPT_ENGINEERING.md`: prompt template rationale + iteration notes
- [ ] `pre-commit` config: ruff + mypy
- [ ] Demo gif (Terminalizer or Kap)
- [ ] GitHub release v0.1.0

**Done when:** repo is public, README has demo gif, someone can clone + run in <5 min.

---

## Project Structure

```
sqlwhisper/
├── src/
│   ├── __init__.py
│   ├── config.py          # pydantic-settings, load config.yaml + .env
│   ├── database/
│   │   ├── connector.py   # SQLAlchemy connect + inspect
│   │   ├── executor.py    # read-only query execution
│   │   └── selector.py    # keyword-based table selection
│   ├── llm/
│   │   ├── client.py      # Ollama HTTP client
│   │   ├── prompt.py      # PromptBuilder
│   │   └── retry.py       # RetryOrchestrator
│   ├── validation/
│   │   ├── parser.py      # sqlglot AST parse
│   │   ├── schema_check.py
│   │   └── safety.py      # blocklist
│   ├── history.py         # SQLite query log
│   └── cli.py             # dev CLI entrypoint
├── app.py                 # Streamlit entrypoint
├── config.yaml
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.111",
    "sqlalchemy>=2.0",
    "sqlglot>=23.0",
    "streamlit>=1.35",
    "ollama>=0.2",
    "pydantic-settings>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "pandas>=2.0",
]

[tool.uv]
dev-dependencies = [
    "ruff", "mypy", "pytest", "pytest-asyncio"
]
```

---

## Risks

| Risk                                     | Mitigation                                                 |
| ---------------------------------------- | ---------------------------------------------------------- |
| `sqlcoder:7b` needs 8GB VRAM             | Fallback to `deepseek-coder:6.7b` (6.5GB); config-driven   |
| Schema too large for context             | Keyword selector caps at 5 tables; warn user if >50 tables |
| LLM ignores LIMIT rule                   | Executor appends LIMIT 500 hard after generation           |
| Validator misses dialect-specific syntax | `sqlglot` dialect param set per DB; test each separately   |
| Day 7 crunch                             | History + explain are stretch features; core is D1–D4      |

---

## Success Metrics (end of day 7)

- 80%+ of natural language questions on a test DB produce correct SQL on first attempt
- Validator catches 100% of blocked keywords before execution
- Retry loop resolves hallucinated column names in ≤2 retries
- `docker compose up` → working UI in <60 seconds
- README + demo gif: someone can clone + run with zero explanation
