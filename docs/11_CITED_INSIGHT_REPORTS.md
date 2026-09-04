# Cited insight reports v1

## Purpose

`cited-report.v1` proves the core reporting invariant before any prose-generation model is introduced: every displayed finding is a stored normalized claim with traceable sentence-level evidence. The report generator does not invent transitions, summaries, recommendations, or source metadata.

## Inclusion rules

- `well_supported`, `supported`, `emerging`, and `disputed` clusters are candidates.
- `weak` clusters are excluded from conclusions and counted in the explanation.
- Every included statement must have at least one `supports` evidence link.
- Every disputed statement must include at least one `supports` and one `contradicts` link.
- Contextual and irrelevant links cannot serve as report citations.
- All supporting and contradicting evidence links are retained, ordered by stance and evidence quality. Contradicting evidence remains visible even when the final label is not disputed.

Statement text is copied from the selected stored claim. The report conclusion is the ordered statement text joined with newlines, so there is no uncited model-written prose.

## Confidence and status

Report confidence is the unweighted mean of included cluster confidence values. The report is `needs_review` when it contains an emerging or disputed statement; otherwise it is `ready`. The response explains this rule and counts included, weak, disputed, and citation-ineligible clusters.

## Immutability and idempotency

The report fingerprint covers generation version, cluster and claim IDs, exact statement text, labels, confidence values, scoring versions, and ordered evidence-link IDs.

- An unchanged evidence state returns the existing report with `idempotent: true`.
- A changed scored evidence state produces a new immutable report version.
- Earlier reports remain readable after later analyst decisions.
- Evidence links cited by a persisted report use a restrictive foreign key so historical provenance cannot be silently deleted.

## Failure behavior

- `REASONING_REQUIRED`: the run has no reasoning execution marker and no scored clusters.
- `INSUFFICIENT_EVIDENCE`: reasoning completed, but no current cluster can meet the report citation rules.
- `RESOURCE_NOT_FOUND`: the requested run or insight does not exist.

Reasoning executions record scoring version, calculation time, included/excluded claim counts, evidence-link count, and cluster count in the analysis-run metrics.

## API

- `POST /api/v1/runs/{run_id}/insights`
- `GET /api/v1/insights/{insight_id}`
- `GET /api/v1/insights/{insight_id}/report`
- `GET /api/v1/insights/{insight_id}/report.md`

The report response includes each citation's evidence-link ID, stance, exact stored passage, canonical URL, publisher, publication/retrieval timestamps, document hash, and evidence-quality score.

## Analyst workspace

The React workspace loads a report by insight UUID or the `?insight=` query parameter. It shows report and finding confidence, review state, exclusion counts, every cited passage, stance, evidence quality, publisher, timestamps, canonical URL, and document hash. The workspace contains no fabricated preview data. It provides deterministic Markdown download and a print stylesheet.

For local development, Vite proxies `/api` to `http://127.0.0.1:8000`. A separately hosted frontend must set `VITE_API_BASE_URL` to the public API origin and the API must explicitly allow that origin. Same-origin deployment needs no frontend override.

## Next boundary

The next report gate is citation correctness on the real evaluation set. A future narrative model may only transform the stored statements if every resulting sentence maps back to the same permitted claim and evidence identifiers and passes citation validation.
