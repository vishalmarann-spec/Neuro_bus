# Gold benchmark data

This directory contains versioned extraction benchmarks. They are evaluation inputs, not production evidence and not demo content.

## Sets

| File | Cases | Status | Intended use |
|---|---:|---|---|
| `synthetic_smoke_v1.json` | 4 | Synthetic | Contract, parser, provenance, and metric smoke tests |
| `public_pilot_v1.json` | 10 | Assistant-verified | Real-source schema and curation pilot only |
| `public_batch_2_v1.json` | 10 | Assistant-verified | Coverage expansion with research, labour-market, temporal, and negative cases |

The two public batches contain 20 official excerpts from 19 publishers/domains across university, government, research, and industry sources. They cover ten task categories, three difficulty levels, five adversarial cases, and two promotion-only passages with no testable claim. The corpus still has no selection-grade development/validation/holdout manifest, double annotation, inter-reviewer agreement measurement, or candidate-model results. It cannot support production-model selection.

## Integrity contract

Every non-synthetic case must include:

- a canonical HTTP(S) source URL, publisher, and source type;
- timezone-aware retrieval and review timestamps;
- an exact UTF-8 excerpt and matching SHA-256 hash;
- an explicit excerpt policy, review status, and reviewer identifier;
- at least one controlled task tag and a declared difficulty;
- entity mention offsets and claim evidence ordinals that resolve to exact stored passages.

Public excerpts are capped at 25 words. `GoldCase` validation fails closed if required metadata is absent, the text hash is stale, the excerpt is too long, provenance is invalid, task tags are duplicated, or a `negative_no_claim` label conflicts with gold claims. Coverage labels are included in the review fingerprint.

## Coverage audit

The audit accepts one or more gold files and emits deterministic coverage counts plus failed selection gates:

```bash
cd backend
uv run python -m app.evaluation.coverage_cli \
  --gold evaluation/gold/public_pilot_v1.json \
  --gold evaluation/gold/public_batch_2_v1.json
```

Add `--require-selection-ready` in CI when auditing a candidate selection corpus. Selection readiness requires at least 100 cases, three source types, six task tags, ten publishers, and at least 10% each adversarial and `negative_no_claim` cases.

## Promotion path

Before any case enters a selection-grade dataset, a named human reviewer must revisit the official URL, compare the exact excerpt, and adjudicate the entities, claims, and evidence offsets. The review CLI records these attestations in an append-only JSONL ledger bound to the exact case fingerprint. It does not edit the gold fixture or silently claim approval.

The selection-manifest command applies only the latest decision for each exact case. A changed fingerprint, later rejection, synthetic case, assistant-only case, undersized dataset, or coverage failure blocks selection. Eligible cases are assigned deterministically to 60% development, 20% validation, and 20% untouched holdout splits.
