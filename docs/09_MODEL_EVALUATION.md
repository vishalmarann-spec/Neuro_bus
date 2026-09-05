# Model evaluation plan

## Purpose

Neuro_Bus selects an extraction model using measured evidence quality, not reputation or a single attractive demo. The same gold cases, prompt version, parser version, and metric implementation must be used for each candidate.

## Current benchmarks

`backend/evaluation/gold/synthetic_smoke_v1.json` contains four synthetic contract tests. Synthetic cases have `source_url: null` and must never appear as product evidence. They verify benchmark mechanics, exact mention offsets, negative/no-claim behaviour, and metric correctness.

`backend/evaluation/gold/public_pilot_v1.json` contains 10 short excerpts manually checked against official pages on 4 September 2026. It covers six university publishers, two government publishers, and one industry report publisher. Each case is labelled `assistant_verified`; no case claims human approval.

The schema rejects a non-synthetic case when its URL, publisher, source type, retrieval timestamp, reviewer, review timestamp, or SHA-256 content hash is missing. It also rejects changed text with a stale hash, public excerpts over 25 words, and gold entity mentions or evidence links that do not resolve to the exact stored passage.

Neither the smoke set nor the pilot is sufficient to select a production model. The pilot exists to prove that real-source curation and integrity enforcement work before paying for candidate-model runs.

### Pilot source policy

- Use only the short excerpt needed to label a claim; public cases are capped at 25 whitespace-delimited words.
- Store the canonical official URL and exact retrieved text. Do not silently clean, paraphrase, or repair the excerpt.
- Recompute `content_hash` from the UTF-8 excerpt after every intentional text change.
- Record `assistant_verified` honestly until a named human reviewer checks the source, labels, offsets, and claim structure.
- Revisit time-sensitive pages before model comparison. A valid historical snapshot can remain in a versioned set, but its retrieval date must not be presented as current truth.

## Production evaluation dataset

Build a versioned set of at least 100 labelled passage/claim examples:

- official university programme and fee pages,
- government or accreditation material,
- research and skills reports,
- employer/job-demand material,
- reputable reporting,
- discussion content clearly marked as lower-trust signals,
- negative passages that contain promotion but no testable claim.

For non-synthetic cases, record the verified source URL, retrieval date, permitted excerpt, content hash, and reviewer. Never invent URLs or present synthetic text as collected evidence.

Split the data before tuning:

- development set for prompt/schema iteration,
- validation set for model comparison,
- untouched holdout set for the final decision.

## Metrics

The benchmark reports per model:

- schema-and-provenance valid rate,
- entity precision, recall, and F1,
- exact mention precision, recall, and F1,
- structured claim precision, recall, and F1,
- evidence-link/citation correctness,
- false-claim rate,
- average latency,
- total input/output tokens,
- total recorded cost.

Confidence calibration is evaluated separately after multi-source scoring exists.

## Initial quality gates

| Metric | Minimum |
|---|---:|
| Schema and provenance valid rate | 0.98 |
| Entity resolution precision | 0.85 |
| Claim precision | 0.80 |
| Citation correctness | 0.95 |
| False-claim rate | <= 0.05 |

Recall, latency, and cost are comparison dimensions rather than excuses to lower the integrity gates.

## Candidate classes

Evaluate at least:

1. A low-cost hosted model with structured JSON output.
2. A higher-accuracy hosted model as the quality ceiling.
3. A local/open model only if available hardware can meet latency and reliability needs.

Record exact provider, model version, date, prompt version, pricing basis, and any retry/repair behaviour. A repaired response counts against first-pass schema reliability.

## Running the scorer

Prediction files may be JSON arrays or JSONL records following `ModelPrediction`.

```bash
cd backend
uv run python -m app.evaluation.cli \
  --gold evaluation/gold/synthetic_smoke_v1.json \
  --predictions evaluation/predictions.json \
  --output evaluation/scorecards.json
```

To exercise the real-source pilot, replace the `--gold` value with `evaluation/gold/public_pilot_v1.json`. Candidate scores from this pilot are diagnostic only and must not be used as the production selection decision.

Generated predictions and scorecards should be kept out of production evidence tables. Commit only small, intentional benchmark artifacts with no secrets or restricted content.
