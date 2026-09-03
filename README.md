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

Planning baseline is locked. Milestone 1 implements projects, research questions, analysis runs, sources, immutable document captures, exact passage offsets, SHA-256 provenance, duplicate protection, database readiness, and the first Alembic migration. Connectors and AI extraction remain deliberately deferred until this storage contract is stable.
