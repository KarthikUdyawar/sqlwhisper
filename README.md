# SQLWhisper 🔍

> Plain English → validated SQL → results. Runs entirely local via Ollama. Zero data leaves your machine.

[![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python)](https://python.org)
[![uv](https://img.shields.io/badge/uv-managed-blueviolet)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](http://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## How it works

```mermaid
flowchart TD
    A([User — plain English question]) --> B[Query Parser\nstrip · normalise]
    B --> C[Schema Layer\nSQLAlchemy introspect · keyword match]
    C --> D[Prompt Builder\ninject schema subset + dialect + rules]
    D --> E[Ollama LLM\nsqlcoder:7b]
    E --> F{SQL Validator}

    F -->|Stage 1 — syntax| G[sqlglot AST parse]
    F -->|Stage 2 — schema| H[column / table diff]
    F -->|Stage 3 — safety| I[BLOCKED_KEYWORDS check]

    G -->|fail| J[Correction prompt\nmax 3 retries]
    H -->|fail| J
    J --> E

    I -->|blocked| K([Hard error — no retry])
    G -->|pass| L[Query Executor\nread-only session · LIMIT 500]
    H -->|pass| L

    L --> M[Result Renderer\nmarkdown table · CSV export · explain]
    M --> N([Streamlit UI])
```

---

## Validation pipeline

```mermaid
flowchart LR
    SQL[Raw SQL from LLM] --> P1

    subgraph Validator
        P1[Stage 1\nSyntax parse\nsqlglot] -->|error| E1[Correction prompt]
        P1 -->|ok| P2[Stage 2\nSchema check\ncolumn · table refs]
        P2 -->|unknown ref| E2[Correction prompt\nwith valid column name]
        P2 -->|ok| P3[Stage 3\nSafety check\nBLOCKED_KEYWORDS]
        P3 -->|blocked| HARD([Hard block\nno retry])
        P3 -->|ok| EXEC
    end

    E1 --> RETRY{Attempt ≤ 3?}
    E2 --> RETRY
    RETRY -->|yes| SQL
    RETRY -->|no| FAIL([Surface error\n+ last SQL attempt])
    EXEC([Query Executor]) --> RESULT([ResultSet])
```

---

## Configuration loading

```mermaid
flowchart LR
    A[os.environ\nAPP_ENV] -->|drives| B

    subgraph Priority - highest wins
        direction TB
        B[env vars\nSQLWHISPER_*] --> C[.env.development\n.env.staging\n.env.production]
        C --> D[.env\nbase fallback]
        D --> E[config/config.yaml\nnon-secret defaults]
    end

    B & C & D & E --> F[Settings\npydantic-settings]

    style B fill:#d4edda
    style E fill:#fff3cd
```

> **Rule:** secrets (DB URLs) → `.env` only via `SecretStr`. Tunables (timeouts, model names, limits) → `config/config.yaml`.

---

## Quick start

### Prerequisites

- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Ollama](https://ollama.com) running locally
- Python 3.12+

### 1. Clone and install

```bash
git clone https://github.com/KarthikUdyawar/sqlwhisper
cd sqlwhisper
make dev          # install all deps including dev
make pc-install   # install pre-commit hooks (once after clone)
```

### 2. Pull the model

```bash
ollama pull sqlcoder:7b
# fallback (lower VRAM):
ollama pull deepseek-coder:6.7b
```

### 3. Configure

```bash
cp .env.example .env.development
```

Edit `.env.development` — add your DB URL:

```env
APP_ENV=development
SQLWHISPER_DATABASES__DEFAULT__URL=postgresql://user:password@localhost:5432/mydb
SQLWHISPER_DATABASES__LOCAL__URL=sqlite:///./dev.db
```

Non-secret tunables (model, timeouts, limits) are already set in `config/config.yaml`.

### 4. Run

```bash
make run   # → http://localhost:8501
```

### Docker (alternative)

```bash
cp .env.example .env   # fill in secrets
docker compose up      # → http://localhost:8501 in <60s
```

---

## Project structure

```text
sqlwhisper/
├── config/
│   └── config.yaml          # non-secret tunables (ollama, app limits)
├── docs/
│   ├── PRD.md
│   └── sprints/
│       └── SPRINT_1.md
├── src/
│   ├── core/
│   │   ├── config.py        # pydantic-settings — Settings + sub-models
│   │   └── constants.py     # all magic strings, numbers, enums
│   ├── database/
│   │   ├── connector.py     # SQLAlchemy connect + schema introspect
│   │   ├── executor.py      # read-only query execution + ResultSet
│   │   └── selector.py      # keyword-based table selection
│   ├── llm/
│   │   ├── client.py        # Ollama HTTP client
│   │   ├── prompt.py        # PromptBuilder
│   │   └── retry.py         # RetryOrchestrator
│   ├── validation/
│   │   ├── parser.py        # sqlglot AST parse
│   │   ├── schema_check.py  # column / table ref validation
│   │   └── safety.py        # BLOCKED_KEYWORDS enforcement
│   └── main.py
├── tests/
│   └── test_config.py
├── app.py                   # Streamlit entrypoint
├── config.yaml              # (see config/)
├── .env.example
├── Makefile
├── pyproject.toml
└── README.md
```

---

## Configuration reference

### `config/config.yaml` — non-secrets only

```yaml
ollama:
  base_url: http://localhost:11434
  model: sqlcoder:7b
  fallback_model: deepseek-coder:6.7b
  timeout_seconds: 30

app:
  max_rows: 500
  max_retries: 3
  max_tables_in_prompt: 5
```

### `.env.<environment>` — secrets + overrides

| Variable                             | Description                              |
| ------------------------------------ | ---------------------------------------- |
| `APP_ENV`                            | `development` / `staging` / `production` |
| `SQLWHISPER_DATABASES__<ALIAS>__URL` | DB connection URL (contains credentials) |
| `SQLWHISPER_OLLAMA__BASE_URL`        | Override Ollama URL                      |
| `SQLWHISPER_OLLAMA__MODEL`           | Override model                           |
| `SQLWHISPER_APP__MAX_ROWS`           | Override row limit                       |

All `config/config.yaml` values are overridable via `SQLWHISPER_<SECTION>__<KEY>` env vars.

---

## Development

```bash
make check      # lint + type-check + tests (full local CI)
make test-cov   # tests with HTML coverage report → htmlcov/
make lint-fix   # auto-fix ruff violations
make type       # mypy --strict
make pc-all     # run all pre-commit hooks on every file
make pc-run HOOK=ruff   # run a single hook
```

### pre-commit hooks

| Hook                  | What it checks                            |
| --------------------- | ----------------------------------------- |
| `trailing-whitespace` | no trailing spaces                        |
| `end-of-file-fixer`   | files end with newline                    |
| `no-commit-to-branch` | protects `master`, `develop`, `release/*` |
| `ruff`                | lint + format                             |
| `bandit`              | security issues                           |
| `gitleaks`            | secrets in code                           |
| `mypy`                | strict type checking                      |

---

## Safety guarantees

```mermaid
flowchart LR
    Q[User question] --> LLM[LLM]
    LLM --> V[Validator\nBLOCKED_KEYWORDS]
    V -->|DROP / DELETE\nUPDATE / INSERT\nTRUNCATE / ALTER\nGRANT / EXEC ...| BLOCK([Blocked — hard stop])
    V -->|safe| EX[Executor\nread-only session]
    EX -->|LIMIT 500\nenforced| R([Results])
```

Two independent guards — if both fail, nothing writes:

1. **Validator** (`src/validation/safety.py`) — AST-level blocklist check before any execution
2. **Executor** (`src/database/executor.py`) — read-only SQLAlchemy session + hard `LIMIT 500` append

---

## Risks & mitigations

| Risk                             | Mitigation                                                                  |
| -------------------------------- | --------------------------------------------------------------------------- |
| `sqlcoder:7b` needs 8 GB VRAM    | Fallback to `deepseek-coder:6.7b` (6.5 GB); config-driven                   |
| Schema too large for context     | Keyword selector caps at 5 tables; warns if DB has >50 tables               |
| LLM ignores LIMIT rule           | Executor appends `LIMIT 500` unconditionally after generation               |
| Hallucinated column names        | Validator diffs against schema cache; correction prompt names valid columns |
| Dialect-specific syntax failures | `sqlglot` dialect param set per DB; tested per dialect separately           |

---

## Roadmap

- **Sprint 1 (current)** — core engine, validator, Streamlit UI, Docker
- **Sprint 2** — embedding-based table selection, MCP server (stdio/SSE), schema cache invalidation
- **Sprint 3** — auth / multi-user, cloud LLM fallback, VS Code integration

---

## License

MIT
