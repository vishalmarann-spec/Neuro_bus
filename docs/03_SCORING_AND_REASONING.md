# Scoring and reasoning specification

## Why three scores exist

- **Source trust:** prior quality of the publisher/source for this type of claim.
- **Evidence quality:** how well one passage supports or contradicts one claim.
- **Claim confidence:** aggregated belief after considering all independent evidence.

These values must not be collapsed into one opaque AI score.

## Source trust v1

Each component is normalized to `[0, 1]` and accompanied by reasons:

| Component | Weight | Meaning |
|---|---:|---|
| Identity/accountability | 0.25 | publisher and authorship are identifiable |
| Primary-source proximity | 0.25 | source directly owns/measures the asserted fact |
| Method transparency | 0.20 | data collection or basis is explained |
| Domain relevance | 0.15 | source is competent for this claim type |
| Historical reliability | 0.15 | reviewed correction/performance history |

`source_trust = weighted mean of known components`

Missing values are excluded from the denominator and reduce a separate completeness flag. Source popularity is never a trust component.

## Evidence quality v1

| Component | Weight |
|---|---:|
| Source trust | 0.30 |
| Directness | 0.25 |
| Extraction confidence | 0.20 |
| Claim/passage specificity | 0.15 |
| Freshness for the claim type | 0.10 |

`evidence_quality = weighted mean of known components`

Freshness decay depends on claim type. A current course price decays quickly; an official programme launch date does not become false merely because it is old.

## Independence and duplicate control

Evidence items share an independence group when they have the same canonical document, syndicate the same text, cite the same upstream study, or come from the same controlled publisher family.

Within a group, the strongest evidence receives weight `1.0`; additional items receive at most `0.25`. This prevents copied articles from masquerading as corroboration.

`claim-confidence.v2` applies these rules transitively using immutable content hashes plus explicit publisher-family and upstream-link metadata. The explanation preserves every shared signal. It does not infer ownership or upstream studies from prose without a recorded provenance assertion.

## Claim aggregation v1

For quality values `q` after independence weighting:

- `support_strength = 1 - product(1 - q_support)`
- `contradiction_strength = 1 - product(1 - q_contradict)`
- `claim_confidence = support_strength * (1 - contradiction_strength)`

The API returns the two strengths as well as final confidence so disagreement stays visible.

### Labels

| Condition | Label |
|---|---|
| contradiction strength >= 0.55 | disputed |
| confidence >= 0.75 and at least two independent sources | well_supported |
| confidence >= 0.55 | supported |
| confidence >= 0.35 | emerging |
| otherwise | weak |

A single source cannot receive `well_supported`, regardless of its score.

## Reasoning engine

The reasoning engine is a constrained pipeline, not a free-form chatbot:

1. Retrieve claims relevant to the research question.
2. Filter invalid/rejected evidence.
3. Group equivalent and conflicting claims.
4. Recalculate deterministic confidence.
5. Select claims using explicit coverage and diversity rules.
6. Ask the model to draft a conclusion using claim IDs only.
7. Validate every drafted sentence against cited claim/evidence IDs.
8. Reject or mark unsupported sentences.
9. Return an explanation containing score contributions and unresolved conflicts.

The current `cited-report.v1` implementation deliberately stops before steps 6–8: it uses stored normalized claim text verbatim and validates deterministic citation rules. A future drafting model may improve readability only after its output can pass the same sentence-level evidence gate.

## Insight confidence

In `cited-report.v1`, insight confidence is the unweighted mean of included cluster confidence values. Each cluster confidence already carries the deterministic contradiction penalty. Coverage counts and excluded weak clusters remain explicit rather than being hidden in a model-selected weight. A future version may add versioned importance weights, but a model cannot set the score.

## Evaluation set

Create at least 100 labelled passage/claim pairs across official university pages, reports, news, job-market material, and discussion content. Label:

- whether a claim is extractable,
- normalized claim,
- entities,
- stance,
- directness,
- citation correctness,
- duplicate/upstream-source group.

Do not tune thresholds on the final holdout set.
