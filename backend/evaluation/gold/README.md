# Gold benchmark data

This directory contains versioned extraction benchmarks. They are evaluation inputs, not production evidence and not demo content.

## Sets

| File | Cases | Status | Intended use |
|---|---:|---|---|
| `synthetic_smoke_v1.json` | 4 | Synthetic | Contract, parser, provenance, and metric smoke tests |
| `public_pilot_v1.json` | 10 | Assistant-verified | Real-source schema and curation pilot only |

The public pilot samples official programme, course, labour-market, skills-report, and fellowship pages. Its source mix is intentionally small and uneven. It has no train/validation/holdout split, no double annotation, no inter-reviewer agreement measurement, and no candidate-model results. It cannot support production-model selection.

## Integrity contract

Every non-synthetic case must include:

- a canonical HTTP(S) source URL, publisher, and source type;
- timezone-aware retrieval and review timestamps;
- an exact UTF-8 excerpt and matching SHA-256 hash;
- an explicit excerpt policy, review status, and reviewer identifier;
- entity mention offsets and claim evidence ordinals that resolve to exact stored passages.

Public excerpts are capped at 25 words. `GoldCase` validation fails closed if required metadata is absent, the text hash is stale, the excerpt is too long, or provenance is invalid.

## Promotion path

Before any case enters a selection-grade dataset, a named human reviewer must revisit the official URL, compare the exact excerpt, adjudicate the entities and claims, and change the status to `human_verified`. The full benchmark then needs at least 100 examples split before tuning into development, validation, and untouched holdout sets, including negative and difficult cases.
