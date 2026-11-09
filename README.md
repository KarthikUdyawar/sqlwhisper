# SQLWhisper

Local, privacy-first natural language → SQL. Upload a CSV or connect a Postgres URL, ask in plain English, get validated read-only SQL, a table and a chart. Nothing leaves your machine.

**Status:** pre-MVP, sprint X1. Plans and decisions live in [`docs/`](docs/).

## Develop

```bash
uv sync
cp .env.example .env
make check      # ruff, mypy --strict, pytest
make tags       # list models on your Ollama
```
