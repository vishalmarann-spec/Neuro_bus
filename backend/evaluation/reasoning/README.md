# Reasoning evaluation scenarios

`real_diagnostic_v1.json` binds each reasoning annotation to an immutable fingerprint of an existing public-source gold case. It covers same-publisher discounting, cross-publisher support, conflicting indicators, and contextual-only evidence.

The scenarios and referenced cases are assistant-verified, so results are diagnostic only. Do not use them to close the production validation gate until a named human has opened the sources, checked the excerpts and stance annotations, and promoted both the source cases and scenarios through a fingerprint-bound review process.

Run the diagnostic from `backend/`:

```bash
python -m app.evaluation.reasoning_cli \
  --gold evaluation/gold/public_pilot_v1.json \
  --gold evaluation/gold/public_batch_2_v1.json \
  --gold evaluation/gold/public_batch_3_v1.json \
  --gold evaluation/gold/public_batch_4_v1.json \
  --scenarios evaluation/reasoning/real_diagnostic_v1.json
```

Add `--require-human-verified` only after the source and reasoning review gates are complete. The command then fails closed if any selected material still lacks human verification.
