# API contract v1

Base path: `/api/v1`

## System

- `GET /health/live` — process is running.
- `GET /health/ready` — required dependencies are usable.

## Projects and questions

- `POST /projects`
- `GET /projects/{project_id}`
- `POST /projects/{project_id}/questions`
- `GET /questions/{question_id}`

## Runs

- `POST /questions/{question_id}/runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `GET /runs/{run_id}/events`

Creating a run accepts optional seed URLs and a source policy. It returns immediately with a run identifier.

## Sources and documents

- `POST /runs/{run_id}/sources` — manually capture source metadata and immutable text; returns the source, document, exact passages, and duplicate status.
- `POST /documents/{document_id}/provenance-links` — record an idempotent `upstream_study` or `syndicated_from` relationship with a canonical URL, actor, and rationale.
- `GET /documents/{document_id}/provenance-links` — inspect the exact dependency assertions used by independence scoring.
- `GET /runs/{run_id}/sources`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/passages`

## Evidence and knowledge

- `POST /documents/{document_id}/extract` — run the configured extraction provider; invalid output is audited and quarantined.
- `POST /runs/{run_id}/reason` — deterministically cluster accepted claims and recalculate versioned evidence/claim scores.
- `GET /runs/{run_id}/ueos`
- `GET /claims/{claim_id}`
- `GET /claims/{claim_id}/evidence`
- `GET /runs/{run_id}/entities`
- `GET /runs/{run_id}/relationships`
- `GET /runs/{run_id}/clusters` — scored claim clusters with component-level explanations.
- `GET /runs/{run_id}/conflicts` — the disputed subset of scored clusters.

## Insights

- `POST /runs/{run_id}/insights` — create an immutable cited report from the current scored clusters; unchanged evidence returns the existing report with `idempotent: true`.
- `GET /insights/{insight_id}` — report metadata, confidence, status, fingerprint, and deterministic conclusion text.
- `GET /insights/{insight_id}/report` — ordered statements with exact passage, evidence-link, publisher, URL, timestamp, and document-hash citations.
- `GET /insights/{insight_id}/report.md` — deterministic Markdown download containing the same findings and citation provenance.

Insight generation returns `409 REASONING_REQUIRED` before scoring and `409 INSUFFICIENT_EVIDENCE` when scoring completed but no cluster satisfies the citation rules.

## Review

- `POST /review/claims/{claim_id}`
- `GET /claims/{claim_id}/reviews`
- `GET /benchmark-reviews/cases` — local human-review queue with aggregate status counts; optional `state` filter.
- `GET /benchmark-reviews/cases/{case_id}` — exact source excerpt, gold labels, current fingerprint, and latest ledger decision.
- `POST /benchmark-reviews/cases/{case_id}/decisions` — append a fingerprint-bound human decision and checklist.
- `POST /review/entities/{entity_id}/merge`
- `POST /review/evidence/{evidence_link_id}`
- `GET /audit-events`

## Model audit

- `GET /model-executions/{execution_id}` — provider/model/prompt/input identifiers, latency, validation result, raw output, and errors.

## Error envelope

```json
{
  "error": {
    "code": "SOURCE_FETCH_TIMEOUT",
    "message": "The source could not be fetched within the configured limit.",
    "retryable": true,
    "details": {},
    "request_id": "req_..."
  }
}
```

## Contract rules

- All externally supplied IDs are validated.
- Lists use cursor pagination.
- Writes accept an idempotency key where retries are likely.
- Scores include their version and component explanation.
- Timestamps are UTC ISO 8601.
- An API response never invents absent source metadata; absent data is `null` with a reason when relevant.
- Re-submitting the same canonical URL and content hash within a run is idempotent and returns the existing capture.
- A conflicting publisher-family declaration for an existing source returns `409` instead of silently changing its independence group.
- Self-referential upstream provenance returns `422`; repeated identical provenance links return the existing record with `duplicate: true`.
- Benchmark approvals require all checklist attestations and the current case fingerprint. These local file-writing routes are disabled outside development unless explicitly injected.
