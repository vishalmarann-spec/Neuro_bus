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

- `POST /runs/{run_id}/sources`
- `GET /runs/{run_id}/sources`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/passages`

## Evidence and knowledge

- `GET /runs/{run_id}/ueos`
- `GET /claims/{claim_id}`
- `GET /claims/{claim_id}/evidence`
- `GET /runs/{run_id}/entities`
- `GET /runs/{run_id}/relationships`
- `GET /runs/{run_id}/conflicts`

## Insights

- `POST /runs/{run_id}/insights`
- `GET /insights/{insight_id}`
- `GET /insights/{insight_id}/report`

## Review

- `POST /review/claims/{claim_id}`
- `POST /review/entities/{entity_id}/merge`
- `POST /review/evidence/{evidence_link_id}`
- `GET /audit-events`

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

