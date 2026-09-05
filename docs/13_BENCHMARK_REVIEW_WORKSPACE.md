# Benchmark human-review workspace

## Purpose

The local review workspace turns assistant-verified benchmark cases into a queue a named human can inspect. It never edits gold fixtures or upgrades their stored `review_status`. Each decision is appended to a separate JSONL ledger and bound to the exact case fingerprint.

## Start locally

Run the API from one terminal:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Run the web client from another:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173/?workspace=review`. Vite proxies `/api` to the local API.

The default development workspace loads:

- `backend/evaluation/gold/public_pilot_v1.json`
- `backend/evaluation/gold/public_batch_2_v1.json`
- `backend/evaluation/gold/public_batch_3_v1.json`

Decisions are appended to `backend/evaluation/reviews/public_corpus_v1.jsonl`. This file is not created until a human submits a decision.

## Review procedure

For each case:

1. Open the official source link.
2. Confirm that the stored excerpt is exact and still appears on the page.
3. Check every entity surface form and character offset.
4. Check every normalized claim, structured object, evidence passage, and rationale.
5. Enter the reviewer's real name and useful notes.
6. Choose `approved`, `changes_requested`, or `rejected` and append the decision.

An approval requires all three attestations. The interface never selects them automatically. Later decisions remain in the ledger and supersede earlier ones without deleting history.

## Integrity and failure behaviour

- Every submission includes the fingerprint displayed when the case loaded.
- If the gold case changes before submission, the API returns `409 REVIEW_CASE_STALE`; refresh and inspect the changed case.
- Invalid or unknown ledger data returns `503 REVIEW_WORKSPACE_DATA_INVALID` instead of silently ignoring history.
- A failed append returns `503 REVIEW_LEDGER_WRITE_FAILED`.
- The routes return `503 REVIEW_WORKSPACE_DISABLED` in test and production environments unless a workspace is explicitly injected.
- The development ledger is intended for a single local reviewer process. Do not expose these unauthenticated file-writing routes on a shared or public server.

## Promotion remains separate

An approved ledger record does not mutate the gold fixture. The selection-manifest workflow later applies the latest exact, approved record and rejects assistant-only, stale, rejected, or changed cases. Review the ledger diff before committing it because it contains reviewer names and notes.
