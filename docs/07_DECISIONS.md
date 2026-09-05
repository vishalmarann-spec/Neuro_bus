# Architecture decision log

## ADR-001: University-first, platform-later

**Decision:** Validate the evidence engine through university programme intelligence before adding other verticals.

**Reason:** A bounded vocabulary and repeatable research questions make evaluation possible. Cross-industry claims remain a design goal, not an MVP requirement.

## ADR-002: Modular monolith

**Decision:** One API codebase plus one worker process.

**Reason:** Maintains clean boundaries without premature distributed-system cost.

## ADR-003: PostgreSQL evidence graph

**Decision:** Store entities and explicit relation tables in PostgreSQL; use pgvector for candidate retrieval.

**Reason:** Provenance and transactional correctness matter more than specialized graph traversal at MVP scale.

## ADR-004: UEO as envelope

**Decision:** UEO v1 composes claim, evidence link, passage, provenance, scores, and versions at the API boundary.

**Reason:** Normalized storage prevents duplication and permits independent correction/versioning.

## ADR-005: Deterministic scoring

**Decision:** Models extract/classify; versioned code calculates trust and confidence.

**Reason:** Scores must be testable and explainable.

## ADR-006: Public data only in MVP

**Decision:** Defer CRM/private source integrations.

**Reason:** Keeps privacy, tenant isolation, and consent complexity outside the evidence-engine validation phase.

## ADR-007: Connector failures are partial outcomes

**Decision:** YouTube or Reddit failures do not block the web-source MVP.

**Reason:** The product must prove evidence quality independently of fragile platform APIs.

## ADR-008: Coverage labels are review-bound selection inputs

**Decision:** Every non-synthetic gold case declares a controlled task category and difficulty. Selection-grade corpora require at least 100 cases, three source types, six task categories, ten publishers, and 10% each adversarial and no-claim negative cases.

**Reason:** Aggregate extraction scores can hide overfitting to easy university descriptions. Binding coverage labels into the case fingerprint makes label changes invalidate earlier approvals and keeps dataset composition auditable.
