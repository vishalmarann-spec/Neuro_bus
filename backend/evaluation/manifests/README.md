# Selection dataset manifests

This directory is reserved for locked manifests created with `python -m app.evaluation.dataset_cli`.

The command refuses to generate a manifest unless it receives at least 100 unique, non-synthetic cases whose latest fingerprint-bound decision is an approved human review. The corpus must also include at least three source types, six task tags, ten publishers, 10% adversarial cases, and 10% `negative_no_claim` cases. The manifest records the coverage report, seed, case fingerprints, and deterministic 60/20/20 development, validation, and untouched holdout assignments.

No selection manifest is committed yet. The current 100-case corpus meets the automated size and diversity gates, but none of its cases has the required fingerprint-bound human approval. Once a manifest has been used for tuning or evaluation, do not rewrite it; create a new version.
