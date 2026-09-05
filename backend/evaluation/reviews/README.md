# Human review ledgers

This directory is reserved for append-only JSONL decisions created with `python -m app.evaluation.review_cli`.

The local web workspace uses `public_corpus_v1.jsonl` by default and writes the same `GoldReviewRecord` format as the CLI. Start the API and frontend, then open `http://localhost:5173/?workspace=review`. See `docs/13_BENCHMARK_REVIEW_WORKSPACE.md` for the checklist and failure behaviour.

No human review records are committed yet. Both public batches remain `assistant_verified` until a named person performs the documented checklist. Do not add placeholder approvals, use another person's identity, or convert assistant verification into human verification without revisiting the official source.

Each record is bound to the case ID, canonical source URL, content hash, task/difficulty coverage labels, and deterministic fingerprint of the document plus gold labels. Changing the case makes an earlier approval stale. Later `changes_requested` or `rejected` decisions supersede earlier approval for selection purposes without deleting history.

Review ledgers may contain reviewer names and notes, so commit only information the reviewer expects to be part of the project audit record. Do not include email addresses, credentials, or private source material.
