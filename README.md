# SQLWhisper

Local, privacy-first natural language → SQL. Upload a CSV or connect a Postgres URL, ask in plain English, get validated read-only SQL, a table and a chart. Nothing leaves your machine.

**Status:** pre-MVP, sprint X1 (X1-1 to X1-7 done: sources, validator, executor, LLM pipeline, API, history, charts, UI, Docker, benchmark; sprint close checks pending). Plans and decisions live in [`docs/`](docs/). Repo layout: [`docs/STRUCTURE.md`](docs/STRUCTURE.md). Rules for AI assistants: [`CLAUDE.md`](CLAUDE.md).

## Quick start (Docker)

Needs Docker and an Ollama with the model pulled (`ollama pull qwen2.5:3b`; `make tags` lists what you have).

```bash
[ -f .env ] || cp .env.example .env
mkdir -p data
docker compose up -d --build
```

Open <http://localhost:8501>, upload a CSV (try `tests/fixtures/bench.csv`) and ask in English, for example "total revenue per month".

- Compose joins the `ollama-net` network of [ollama-hub](https://github.com/KarthikUdyawar/ollama-hub) and reaches Ollama at `http://ollama:11434` ([D-36](docs/DECISION.md)). Start the hub first. For another Ollama, set `DOCKER_OLLAMA_URL` in `.env` and remove the `ollama-net` entries from `docker-compose.yml`.
- Keep the `mkdir -p data`. Without it Docker creates `data/` as root and the API (uid 1000) cannot write to it.
- Ports are bound to `127.0.0.1` because the API has no auth ([D-38](docs/DECISION.md)). Use an SSH tunnel from another machine.
- Streamlit usage statistics and the public-IP lookup are off ([D-37](docs/DECISION.md)).

## Develop

```bash
uv sync
cp .env.example .env
make check      # ruff, mypy --strict, pytest
make tags       # list models on your Ollama
make smoke      # opt-in: one real question against Ollama
make bench      # opt-in: 20-question benchmark, MODEL=<name> picks the model
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

## Configuration

Environment only, read from `.env` (copy of `.env.example`). Compose overrides `OLLAMA_URL`, `DATA_DIR` and `API_URL` inside the containers.

| Variable           | Default                  | Meaning                             |
| ------------------ | ------------------------ | ----------------------------------- |
| `OLLAMA_URL`       | `http://localhost:11434` | Ollama base URL                     |
| `OLLAMA_MODEL`     | `qwen2.5:3b`             | Model for SQL generation            |
| `OLLAMA_TIMEOUT_S` | `60`                     | Per-request timeout to Ollama       |
| `MAX_ROWS`         | `500`                    | Row cap enforced on every query     |
| `MAX_RETRIES`      | `2`                      | Correction rounds (3 attempts)      |
| `QUERY_TIMEOUT_S`  | `15`                     | Statement timeout                   |
| `MAX_UPLOAD_MB`    | `50`                     | CSV size limit                      |
| `DATA_DIR`         | `./data`                 | Uploads and history                 |
| `API_URL`          | `http://localhost:8000`  | UI to API                           |
| `DOCKER_OLLAMA_URL`| `http://ollama:11434`    | Compose only: Ollama from the api container |

## Benchmark

`make bench MODEL=<name>` runs 20 questions on a fixed 96-row CSV (`tests/fixtures/`) against a real Ollama and compares result values, not SQL text. First-attempt accuracy, one run, temperature 0, on a 4 GB GPU:

| Model                 | Correct | Median  | Note                              |
| --------------------- | ------- | ------- | --------------------------------- |
| `qwen2.5:3b` (default) | 16/20   | 0.4 s   |                                   |
| `qwen2.5:3b-gpu`      | 16/20   | 0.3 s   | ollama-hub build                  |
| `qwen2.5:7b-instruct` | 16/20   | 1.8 s   |                                   |
| `llama3.2:3b`         | 12/20   | 0.5 s   |                                   |
| `qwen3:4b`            | 11/20   | 27 s    | 6 of 20 hit the 60 s timeout      |

Method and caveats: [D-39](docs/DECISION.md).

## Known limits

- The prompt carries the schema only, no sample values. Questions that depend on how a value is spelled or how missing values are stored often fail (benchmark Q08, Q10, Q19).
- 20 questions and one run cannot separate models that differ by one or two answers.
- The benchmark does not show the retry path working. It ran once and ended in a wrong answer. Unit tests cover it with a fake model.
- The Postgres source is tested without a live server and has not been run against a real database.
- The first query after a cold model load can hit `OLLAMA_TIMEOUT_S` on a small GPU.
- No auth: the API and UI listen on loopback only.
