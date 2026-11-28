FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app
WORKDIR /app
USER app

# README.md and src/ must exist before sync: pyproject uses readme + uv_build.
COPY --chown=app:app . .
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"
