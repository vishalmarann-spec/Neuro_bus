# Neuro_Bus engineering rules

## Product invariants

- Never generate an insight without linked evidence.
- Never treat a model-generated statement as source evidence.
- Preserve exact source URL, retrieval time, document hash, and quoted passage.
- Keep source trust, evidence quality, and claim confidence as separate values.
- Contradictory evidence must remain visible; never silently discard it.
- A connector failure must produce an explicit unavailable/partial status, not fabricated fallback data.

## Development rules

- Build vertical slices and test them end to end.
- Keep provider-specific SDKs behind adapters.
- Use database migrations for schema changes.
- Prefer deterministic rules for scoring; use models for extraction and classification.
- Log model name, prompt version, input hash, and output validation result.
- Do not add Neo4j, Kubernetes, Kafka, or microservices during MVP.
- Do not expose secrets in code, logs, fixtures, or commits.

## Definition of done

A feature is complete only when it has typed interfaces, validation, tests, failure behavior, observability, and documentation.

