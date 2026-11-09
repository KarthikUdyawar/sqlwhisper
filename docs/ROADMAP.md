# SQLWhisper — Roadmap

Status: **pre-MVP**. Sprint X1 in progress (see `TODO.md`).

Rule: nothing enters a sprint until the previous sprint's exit criteria are met. Anything speculative lives in "Later".

---

## v0.2 — MVP (Sprint X1)

**Goal:** upload one CSV or connect a Postgres URL, ask in English, get validated read-only SQL, table, chart.

- FastAPI backend + Streamlit UI
- Sources: single CSV, Postgres URL
- AST validator + retry (max 2) + read-only executor
- Deterministic chart picker
- Follow-ups via last 3 Q/SQL pairs
- Query history (last 20)
- Docker Compose, model benchmark, README

**Exit criteria:** see PRD "Success metrics".

---

## v0.3 — Accuracy (Sprint X2)

**Goal:** raise first-attempt SQL accuracy and handle messier data.

- Few-shot examples in prompt, selected per dialect
- Column descriptions / sample values (types and distinct categories only, never raw rows) to cut hallucinated filters
- Multiple CSVs in one session, joins allowed
- Result-aware retry (empty result → ask model to re-check filters, once)
- Benchmark suite as a repeatable `make bench` with a fixed question set
- "Explain this result" (NL summary)

**Exit criteria:** ≥90% first-attempt accuracy on the benchmark with the default model.

---

## v0.4 — Reach (Sprint X3)

**Goal:** more sources, smarter table selection.

- MySQL source
- Excel upload (`.xlsx`, one sheet per table)
- Embedding-based table selector (`nomic-embed-text`, already available locally)
- Schema cache invalidation on DDL change
- Persistent source registry (store non-secret metadata only)
- Export chart as PNG / HTML

**Exit criteria:** selector beats keyword matching on a >20-table fixture.

---

## v0.5 — Team use (Sprint X4)

**Goal:** safe to share on a LAN.

- Auth (single shared password first, OAuth later if needed)
- Per-source access control
- Rate limiting
- Structured logging, request IDs
- Per-user query history

**Exit criteria:** two users can work in parallel without seeing each other's sources.

---

## Later (unscheduled, needs a real use case first)

- MCP server wrapper over the API
- Cloud LLM fallback (opt-in, off by default, breaks the privacy promise → explicit warning)
- Dashboard mode (pinned charts)
- Scheduled reports
- Multi-agent split (SQL / chart / insight)
- Fine-tuned small text-to-SQL model
- Voice input

---

## Principles for every sprint

1. Privacy first: no row data or credentials leave the machine, none in prompts beyond what a feature explicitly needs.
2. Read-only is non-negotiable.
3. Test-first. LLM is faked in unit tests.
4. KISS before SOLID: add an abstraction on the second use, not the first guess.
5. Every sprint ends with `make check` green and a runnable `docker compose up`.
