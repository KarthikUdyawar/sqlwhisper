.PHONY: install dev lint lint-fix type test test-cov check run cli \
	pc-install pc pc-all pc-push pc-run pc-update \
	docker-up docker-down clean

# ── Dependencies ──────────────────────────────────────────────────────────────
install:
	uv sync

dev:
	uv sync --dev

# ── Linting / formatting ──────────────────────────────────────────────────────
lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

# ── Type checking ─────────────────────────────────────────────────────────────
type:
	uv run mypy src/

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# ── Full local CI (lint + type + test) ────────────────────────────────────────
check: lint type test

# ── pre-commit ────────────────────────────────────────────────────────────────
## Install hooks into .git/hooks (run once after clone)
pc-install:
	uv run pre-commit install --hook-type pre-commit
	uv run pre-commit install --hook-type pre-push
	uv run pre-commit install --hook-type commit-msg

## Run hooks on staged files only (mirrors what git commit triggers)
pc:
	uv run pre-commit run

## Run hooks on ALL files (use in CI or before a big PR)
pc-all:
	uv run pre-commit run --all-files

## Run pre-push hooks only (mirrors what git push triggers)
pc-push:
	uv run pre-commit run --hook-stage pre-push --all-files

## Run a single hook by id, e.g.: make pc-run HOOK=ruff
pc-run:
	ifndef HOOK
		$(error HOOK is not set. Usage: make pc-run HOOK=<hook-id>)
	endif
		uv run pre-commit run $(HOOK) --all-files

## Update all hook versions to latest (then pin + commit)
pc-update:
	uv run pre-commit autoupdate

# ── App ───────────────────────────────────────────────────────────────────────
run:
	uv run streamlit run app.py

cli:
	PYTHONPATH=src uv run python -m main $(ARGS)

# ── Docker ────────────────────────────────────────────────────────────────────
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov
