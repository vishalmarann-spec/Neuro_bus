# Selection dataset manifests

This directory is reserved for locked manifests created with `python -m app.evaluation.dataset_cli`.

The command refuses to generate a manifest unless it receives at least 100 unique, non-synthetic cases whose latest fingerprint-bound decision is an approved human review. It records the seed, case fingerprints, and deterministic 60/20/20 development, validation, and untouched holdout assignments.

No selection manifest is committed yet because the current 10-case pilot does not meet those gates. Once a manifest has been used for tuning or evaluation, do not rewrite it; create a new version.
