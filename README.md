# SQLWhisper

Local, privacy-first natural language → SQL. Upload a CSV or connect a Postgres URL, ask in plain English, get validated read-only SQL, a table and a chart. Nothing leaves your machine.

**Status:** pre-MVP, sprint X1 (X1-1 to X1-4 done: sources, validator, executor, LLM pipeline; API and UI next). Plans and decisions live in [`docs/`](docs/). Repo layout: [`docs/STRUCTURE.md`](docs/STRUCTURE.md). Rules for AI assistants: [`CLAUDE.md`](CLAUDE.md).

## Develop

```bash
uv sync
cp .env.example .env
make check      # ruff, mypy --strict, pytest
make tags       # list models on your Ollama
make smoke      # opt-in: one real question against Ollama
make tree       # regenerate docs/STRUCTURE.md
```
