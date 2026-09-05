# Neuro_Bus

Neuro_Bus is an evidence-intelligence system that turns public market signals into traceable, confidence-aware business insights.

The first vertical is university programme intelligence: identifying emerging course demand, competitor positioning, pricing signals, and gaps in university offerings. The engine is designed so additional industries can be added later without rewriting the evidence pipeline.

## Product promise

Every insight must answer four questions:

1. What is the claim?
2. Which exact evidence supports or contradicts it?
3. How reliable and independent are those sources?
4. Why did the system assign this confidence level?

No uncited narrative is considered a valid output.

## MVP workflow

`Research question -> source discovery -> document capture -> passage extraction -> claim extraction -> entity resolution -> corroboration/contradiction -> scored insight -> cited report`

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- API: FastAPI, Python 3.12
- Data: PostgreSQL, pgvector
- Background work: Redis and an async worker
- Migrations: Alembic
- Tests: pytest
- Model access: provider-independent adapter

## Repository map

- `backend/` API, pipeline, domain rules, persistence, and workers
- `frontend/` analyst workspace
- `docs/` product and engineering specifications

Start with [docs/00_PRODUCT_SPEC.md](docs/00_PRODUCT_SPEC.md) and [docs/06_EXECUTION_BOARD.md](docs/06_EXECUTION_BOARD.md).

## Current status

Planning baseline is locked. Milestone 1 provides trustworthy evidence storage. Milestone 2 adds provider-independent, provenance-validated extraction and append-only review. Milestone 3 provides conservative entity resolution, deterministic claim clustering, duplicate-aware support/contradiction scoring, and explicit explanations. Milestone 4 creates immutable, idempotent cited reports and exposes them through a responsive analyst workspace with exact passages, conflicts, confidence rationale, Markdown download, and print output. Evaluation now includes synthetic contract tests plus a 10-case, assistant-verified public-source pilot with enforced URL, timestamp, hash, excerpt-policy, and provenance integrity. The pilot is deliberately not production-model-selection evidence; human review, the 100-case split dataset, real source connectors, and upstream citation-family detection remain open work.
