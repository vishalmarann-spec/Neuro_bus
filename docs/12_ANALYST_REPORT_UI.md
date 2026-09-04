# Analyst report workspace

## Primary workflow

1. Generate an insight through `POST /api/v1/runs/{run_id}/insights`.
2. Open the frontend and enter the returned insight UUID.
3. Review report confidence, included and excluded counts, and any review warning.
4. Open each finding's evidence list and inspect every supporting or contradicting passage.
5. Follow the canonical source URL, download deterministic Markdown, or print the report.

The URL query `?insight={uuid}` loads a report directly and makes a reviewed report linkable without copying its contents into the page.

## Display rules

- Green denotes support or a ready state.
- Amber denotes emerging evidence or a report needing review.
- Red denotes contradiction or a disputed finding.
- Confidence is always shown numerically; colour is never the only signal.
- Source metadata uses the API values without replacement or inferred publication dates.
- Missing publication dates display `Not supplied`.
- Long identifiers and URLs remain available through links or title text without breaking the layout.

## States

- Empty: asks for an insight UUID and explains the three-step review workflow.
- Loading: retains the current input and exposes an assistive status message.
- Invalid input: rejects malformed UUIDs without sending a request.
- API failure: shows the server's explicit error message when available.
- Success: renders the report summary, findings, and complete citation list.

## Export

`GET /api/v1/insights/{insight_id}/report.md` downloads a deterministic Markdown evidence record. The backend escapes untrusted source text before rendering Markdown. The Print action uses a dedicated high-contrast stylesheet and removes workspace controls.

## Runtime configuration

The frontend uses same-origin `/api` requests by default. During local development, Vite proxies those requests to `http://127.0.0.1:8000`. Set `VITE_API_BASE_URL` at build time only when the API is hosted on a different origin.

## Current boundary

The workspace does not list or search reports because the backend does not yet expose a report-index endpoint. Authentication, deployment-origin policy, and broader analyst project navigation belong to demo hardening rather than this evidence-report slice.
