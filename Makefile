.RECIPEPREFIX := >
.PHONY: check lint type test tags smoke api

check: lint type test

lint:
> uv run ruff check . && uv run ruff format --check .

type:
> uv run mypy src tests

test:
> uv run pytest -m "not ollama"

tags:
> curl -s $${OLLAMA_URL:-http://localhost:11434}/api/tags | jq .

smoke:
> uv run pytest -m ollama -s

api:
> uv run uvicorn sqlwhisper.api:create_app --factory --reload --port 8000
