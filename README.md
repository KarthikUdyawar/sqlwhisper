# SQLWhisper

Local, privacy-first natural language → SQL. Upload a CSV or connect a Postgres URL, ask in plain English, get validated read-only SQL, a table and a chart. Nothing leaves your machine.

**Status:** pre-MVP, sprint X1 (X1-1 to X1-6 done: sources, validator, executor, LLM pipeline, API, history, charts, UI; Docker and benchmark next). Plans and decisions live in [`docs/`](docs/). Repo layout: [`docs/STRUCTURE.md`](docs/STRUCTURE.md). Rules for AI assistants: [`CLAUDE.md`](CLAUDE.md).

## Develop

```bash
uv sync
cp .env.example .env
make check      # ruff, mypy --strict, pytest
make tags       # list models on your Ollama
make smoke      # opt-in: one real question against Ollama
make api        # start the API on :8000
make ui         # start the Streamlit UI on :8501
make tree       # regenerate docs/STRUCTURE.md
```

## Try the API

With `make api` running and Ollama up (needs `jq`):

```bash
SRC=$(curl -s -F "file=@data/sales.csv" localhost:8000/sources/csv | jq -r .source_id)
curl -s localhost:8000/query -H "Content-Type: application/json" \
  -d "{\"source_id\": \"$SRC\", \"question\": \"total by region\"}" | jq
curl -s localhost:8000/history | jq
```

Any CSV works in place of `data/sales.csv`. Response shape: [`docs/PRD.md`](docs/PRD.md#api).
