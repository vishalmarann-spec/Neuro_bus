# System architecture

## Architecture choice

Use a modular monolith plus a separate worker process. This keeps deployment and debugging manageable while preserving module boundaries that could later become services.

## Runtime components

1. **Web application:** analyst interface and report viewer.
2. **FastAPI application:** projects, sources, evidence, claims, insights, review actions.
3. **Worker:** document fetching, parsing, chunking, extraction, embedding, and analysis jobs.
4. **PostgreSQL + pgvector:** transactional data, provenance, graph-like relationships, and semantic retrieval.
5. **Redis:** job queue and short-lived coordination only; never the authoritative evidence store.
6. **Blob storage adapter:** immutable raw captures. Local storage in development; S3-compatible storage later.
7. **Model adapter:** structured extraction through a configured provider; the rest of the system remains provider-independent.

## Module boundaries

| Module | Owns | Must not own |
|---|---|---|
| Projects | research questions, run lifecycle | extraction logic |
| Ingestion | discovery, fetch, parsing, snapshots | business conclusions |
| Evidence | documents, passages, provenance | source discovery |
| Knowledge | entities, claims, evidence links, relations | report prose |
| Scoring | trust, quality, confidence, explanations | source fetching |
| Insights | synthesis and citations | changing raw evidence |
| Review | analyst decisions and audit events | destructive history rewriting |
| Providers | web/model/storage integrations | domain rules |

## Pipeline states

`queued -> discovering -> fetching -> parsing -> extracting -> resolving -> scoring -> synthesizing -> completed`

Terminal alternatives: `completed_partial`, `failed`, `cancelled`.

Each stage records start time, finish time, input/output counts, error code, retryability, and implementation version.

## Data flow

1. Create an analysis run for a research question.
2. Discover or accept candidate URLs.
3. Apply URL policy and capture allowed documents.
4. Store immutable raw content plus metadata and content hash.
5. Create passages with deterministic offsets.
6. Extract structured claim candidates and entities from passages.
7. Validate every extracted claim against its cited passage.
8. Resolve entities and cluster semantically equivalent claims.
9. Classify evidence links as support, contradict, contextual, or irrelevant.
10. Calculate deterministic source, evidence, and claim scores.
11. Generate insights only from stored claim/evidence identifiers.
12. Validate citations and expose the result for analyst review.

## Important design decisions

- The Universal Evidence Object (UEO) is an API envelope/view, not a single oversized database table.
- The evidence graph begins in PostgreSQL using explicit relation tables. Neo4j is reconsidered only after graph queries become a demonstrated bottleneck.
- Embeddings help retrieve and cluster candidates; they never decide truth.
- Raw captures and their hashes are immutable. Corrections create new versions/audit records.
- Model output enters the database only after schema and provenance validation.

## Failure behavior

- A source failure affects that source, not the entire run.
- A model validation failure is retained for debugging but never promoted to evidence.
- A run may complete as partial when minimum evidence criteria are met.
- Retries use capped exponential backoff and idempotency keys.
- Unsupported content types are recorded explicitly.

## Deployment phases

- Development: local API, worker, PostgreSQL/pgvector, Redis.
- Demo: one container host plus managed PostgreSQL and Redis.
- Later production: separate API/worker scaling, object storage, authentication, backups, monitoring.

