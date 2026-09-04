# Domain and evidence model

## Core records

| Record | Essential fields |
|---|---|
| Project | id, name, vertical, owner, created_at |
| ResearchQuestion | id, project_id, text, scope, status |
| AnalysisRun | id, question_id, state, versions, timestamps, metrics |
| Source | id, canonical_domain, publisher, type, trust_profile |
| Document | id, source_id, canonical_url, retrieved_at, published_at, content_hash, storage_uri, parser_version |
| Passage | id, document_id, ordinal, start_offset, end_offset, exact_text, text_hash |
| Entity | id, type, canonical_name, normalized_name, aliases |
| EntityMention | id, entity_id, passage_id, surface_text, offsets, confidence |
| Claim | id, subject_entity_id, predicate, object_value/entity_id, qualifiers, normalized_text, extraction_confidence |
| EvidenceLink | id, claim_id, passage_id, stance, directness, extraction_confidence, rationale |
| Relationship | id, from_entity_id, type, to_entity_id, evidence_link_id |
| ClaimCluster | id, canonical_claim_id, topic, cluster_version |
| Insight | id, run_id, title, conclusion, confidence, explanation, status |
| InsightStatement | insight_id, cluster_id, claim_id, text, label, confidence, display_order |
| InsightCitation | statement_id, evidence_link_id, display_order |
| ReviewDecision | id, target_type, target_id, action, reason, actor, timestamp |
| ModelExecution | id, task, provider, model, prompt_version, input_hash, validation_status, latency, token/cost metadata |

## Controlled values

### Entity types

`university`, `programme`, `course`, `skill`, `technology`, `employer`, `industry`, `location`, `credential`, `price`, `date`, `metric`, `organization`.

### Evidence stance

- `supports`: passage increases belief in the normalized claim.
- `contradicts`: passage provides incompatible evidence.
- `contextual`: passage explains scope but neither supports nor contradicts directly.
- `irrelevant`: candidate was rejected during validation.

### Claim review status

`machine_extracted`, `accepted`, `corrected`, `rejected`, `needs_review`.

## Universal Evidence Object v1

The UEO exposed through APIs contains:

```json
{
  "id": "ueo_...",
  "claim": {
    "id": "clm_...",
    "normalized_text": "Demand for AI security education is increasing",
    "subject": {"id": "ent_...", "name": "AI security education"},
    "predicate": "demand_trend",
    "object": {"value": "increasing"},
    "qualifiers": {"region": null, "time_period": null}
  },
  "evidence": {
    "stance": "supports",
    "passage_id": "pas_...",
    "quote": "...exact stored passage...",
    "directness": 0.86
  },
  "provenance": {
    "url": "https://example.org/page",
    "publisher": "Example Publisher",
    "published_at": null,
    "retrieved_at": "2026-09-03T00:00:00Z",
    "document_hash": "sha256:..."
  },
  "scores": {
    "source_trust": 0.72,
    "evidence_quality": 0.78,
    "extraction_confidence": 0.91
  },
  "versions": {
    "schema": "ueo.v1",
    "extractor": "claim-extractor.v1",
    "scoring": "evidence-score.v1"
  }
}
```

## Invariants

- Every EvidenceLink references one stored Passage and one Claim.
- Passage text must match the stored document offsets and hash.
- Deleting a source must not silently remove audit history.
- Insight confidence is derived from linked claims; it is not accepted directly from a language model.
- Duplicate documents are linked but not counted as independent corroboration.
- Every report statement has supporting evidence; a disputed statement also has contradicting evidence.
- Evidence links referenced by a persisted report cannot be deleted, preserving historical citation provenance.
