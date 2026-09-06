# Model evaluation plan

## Purpose

Neuro_Bus selects an extraction model using measured evidence quality, not reputation or a single attractive demo. The same gold cases, prompt version, parser version, and metric implementation must be used for each candidate.

## Current benchmarks

`backend/evaluation/gold/synthetic_smoke_v1.json` contains four synthetic contract tests. Synthetic cases have `source_url: null` and must never appear as product evidence. They verify benchmark mechanics, exact mention offsets, negative/no-claim behaviour, and metric correctness.

`backend/evaluation/gold/public_pilot_v1.json` contains 10 short excerpts checked against official pages on 4 September 2026. `backend/evaluation/gold/public_batch_2_v1.json` adds 10 excerpts checked on 5 September 2026, `backend/evaluation/gold/public_batch_3_v1.json` adds 20, and `backend/evaluation/gold/public_batch_4_v1.json` adds 60 more checked the same day. Together they cover 100 cases from 40 publishers across 45 domains and university, government, research, industry, and accreditation-body sources. Each case is labelled `assistant_verified`; no case claims human approval.

The combined corpus declares 15 task categories and basic/intermediate/adversarial difficulty. Twenty-seven cases are adversarial, including temporal, negated, and methodology-sensitive facts, and 10 are promotion-only negative passages with no testable claim. The corpus passes the automated size and diversity gate. Promotion remains blocked until all selected cases have current, fingerprint-bound human approvals.

The schema rejects a non-synthetic case when its URL, publisher, source type, retrieval timestamp, reviewer, review timestamp, SHA-256 content hash, or task tag is missing. It also rejects changed text with a stale hash, public excerpts over 25 words, contradictory no-claim labels, and gold entity mentions or evidence links that do not resolve to the exact stored passage. Difficulty and task labels are included in the human-review fingerprint.

Neither the smoke set nor the assistant-verified public corpus is sufficient to select a production model. The 100-case corpus proves that real-source curation, integrity enforcement, and coverage gating work before human review and paid candidate-model runs.

The same boundary applies to deterministic reasoning validation. `backend/evaluation/reasoning/real_diagnostic_v1.json` references existing public cases by exact fingerprint and currently exercises supported, well-supported, disputed, and weak outcomes. Its 4/4 result is a regression diagnostic, not human validation; the reasoning CLI marks the report diagnostic-only and provides a strict human-verification gate.

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

Before promotion, run the deterministic coverage audit. A selection corpus must contain at least three source types, six task tags, ten publishers, and at least 10% each adversarial and `negative_no_claim` cases. These are minimum anti-overfitting gates, not target weights; future dataset versions may strengthen them based on observed error slices.

```bash
uv run python -m app.evaluation.coverage_cli \
  --gold evaluation/gold/public_pilot_v1.json \
  --gold evaluation/gold/public_batch_2_v1.json \
  --gold evaluation/gold/public_batch_3_v1.json \
  --gold evaluation/gold/public_batch_4_v1.json
```

Split the data before tuning:

- development set for prompt/schema iteration,
- validation set for model comparison,
- untouched holdout set for the final decision.

## Human-review workflow

Review decisions live in append-only JSONL ledgers and are separate from the gold files. An approval is valid only when the reviewer confirms that the official URL was opened, the excerpt matches it, and the entities, claims, and evidence offsets were checked. The record stores the source URL, content hash, exact case fingerprint, named reviewer, decision, notes, and timezone-aware timestamp.

The tool rejects approvals with an incomplete checklist or non-human labels such as `codex`. Changing any review-bound document or gold-label field changes the fingerprint and makes the prior approval stale. The latest `changes_requested` or `rejected` decision also prevents promotion.

```bash
cd backend
uv run python -m app.evaluation.review_cli \
  --gold evaluation/gold/public_pilot_v1.json \
  --case-id public_cmu_msaii_requirements \
  --ledger evaluation/reviews/public_pilot_v1.jsonl \
  --reviewer "Reviewer full name" \
  --decision approved \
  --notes "Checked source, excerpt, labels, and offsets." \
  --source-url-opened \
  --excerpt-matches-source \
  --entities-and-claims-checked
```

Do not use another person's name or check an attestation that was not actually performed. No human review records are committed yet.

For the same workflow in a reviewer-friendly interface, start the local API and frontend and open `http://localhost:5173/?workspace=review`. The workspace shows queue status, official source links, exact excerpts and hashes, gold entities and offsets, structured claims and evidence, the latest decision, and the required attestations. It writes the same append-only record format as the CLI. The web routes are deliberately disabled outside local development; see `docs/13_BENCHMARK_REVIEW_WORKSPACE.md`.

## Selection-manifest workflow

The manifest command combines one or more gold files with the latest review ledger. It fails closed unless there are at least 100 unique, non-synthetic, currently human-verified cases. Eligible cases are deterministically assigned by a recorded seed to 60% development, 20% validation, and 20% untouched holdout splits; each assignment is bound to its case fingerprint.

```bash
uv run python -m app.evaluation.dataset_cli \
  --gold evaluation/gold/university_programmes_v1.json \
  --gold evaluation/gold/university_market_signals_v1.json \
  --reviews evaluation/reviews/university_selection_v1.jsonl \
  --dataset-id university-selection-v1 \
  --seed neuro-bus-selection-v1 \
  --output evaluation/manifests/university_selection_v1.json
```

Create and commit the manifest before prompt tuning. Never change the seed or case membership after viewing validation or holdout results; create a new dataset version instead.

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

Generate predictions only after deliberately configuring a provider. Live requests require the explicit cost-confirmation flag. Until the review ledger contains exact human approvals, the assistant-verified corpus can be used only with the diagnostic override:

```bash
cd backend
MODEL_PROVIDER=openai \
MODEL_NAME='your-pinned-model-id' \
MODEL_API_KEY='your-server-side-api-key' \
uv run python -m app.evaluation.run_cli \
  --gold evaluation/gold/public_pilot_v1.json \
  --limit 5 \
  --output evaluation/openai_diagnostic_run.json \
  --pricing-basis "OpenAI pricing page, checked YYYY-MM-DD" \
  --allow-assistant-verified-diagnostic \
  --confirm-live-api-cost
```

The generator writes a `benchmark-run.v1` artifact containing provider, exact model identifier, prompt version, timestamps, diagnostic status, case fingerprints, successful predictions, sanitized per-case failures, token usage, and configured cost estimates. It refuses to overwrite an existing artifact without `--overwrite`; a partial run is saved and exits non-zero.

After human review, pass the append-only ledger with `--reviews` and omit the diagnostic override. Start with a small development slice before running the full corpus. Never use validation or holdout cases for prompt tuning.

The scorer accepts a `benchmark-run.v1` artifact or legacy JSON array/JSONL records following `ModelPrediction`.

```bash
cd backend
uv run python -m app.evaluation.cli \
  --gold evaluation/gold/public_pilot_v1.json \
  --gold evaluation/gold/public_batch_2_v1.json \
  --gold evaluation/gold/public_batch_3_v1.json \
  --gold evaluation/gold/public_batch_4_v1.json \
  --predictions evaluation/predictions.json \
  --output evaluation/scorecards.json
```

`--gold` is repeatable, and duplicate case IDs across files fail closed. For the synthetic smoke run, use only `evaluation/gold/synthetic_smoke_v1.json`. Candidate scores from assistant-verified public batches are diagnostic only and must not be used as the production selection decision.

Generated predictions and scorecards should be kept out of production evidence tables. Commit only small, intentional benchmark artifacts with no secrets or restricted content.
