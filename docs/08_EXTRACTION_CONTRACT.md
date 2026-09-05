# One-source extraction contract

## Boundary

The extraction model receives document metadata and numbered passages. It returns candidate entities, exact entity mentions, normalized claims, and evidence references. The model never writes to storage directly and never assigns source-trust or claim-confidence scores.

Production configuration defaults to the disabled adapter. Tests use the deterministic fake adapter. An opt-in OpenAI Responses API adapter implements the same protocol; choosing it does not change persistence or validation. It requests JSON output, disables provider-side response storage for the request, records token usage, and leaves final schema and provenance enforcement to Neuro_Bus.

## Provider configuration

Keep secrets in the server environment, never in frontend code or committed files:

```dotenv
MODEL_PROVIDER=openai
MODEL_NAME=your-pinned-model-id
MODEL_API_KEY=your-server-side-api-key
MODEL_TIMEOUT_SECONDS=60
MODEL_MAX_OUTPUT_TOKENS=4096
```

The application fails during provider construction when `MODEL_PROVIDER=openai` lacks a key or model name. HTTP errors, timeouts, refusals, incomplete responses, malformed provider responses, and missing output are reported as explicit unavailable results. Provider response bodies and API keys are not copied into client-facing errors.

Optional `MODEL_INPUT_COST_PER_MILLION_USD` and `MODEL_OUTPUT_COST_PER_MILLION_USD` values enable a per-call cost estimate from reported token counts. Configure both or neither, and record the pricing source and date with every benchmark run.

## Input

```json
{
  "document_id": "uuid",
  "title": "AI Security Programme",
  "canonical_url": "https://example.edu/programmes/ai-security",
  "passages": [
    {
      "ordinal": 0,
      "passage_id": "uuid",
      "text": "Example University launched an AI security programme in 2026."
    }
  ]
}
```

All passage content is untrusted data. Provider prompts must explicitly instruct the model to ignore commands contained inside source text.

## Required output

```json
{
  "entities": [
    {
      "local_id": "university_1",
      "entity_type": "university",
      "canonical_name": "Example University",
      "aliases": [],
      "mentions": [
        {
          "passage_ordinal": 0,
          "surface_text": "Example University",
          "start_offset": 0,
          "end_offset": 18,
          "confidence": 0.99
        }
      ]
    }
  ],
  "claims": [
    {
      "subject_local_id": "university_1",
      "predicate": "launched_programme",
      "object_value": {"programme": "AI security"},
      "qualifiers": {"year": 2026},
      "normalized_text": "Example University launched an AI security programme in 2026.",
      "extraction_confidence": 0.94,
      "evidence": [
        {
          "passage_ordinal": 0,
          "stance": "supports",
          "directness": 0.98,
          "extraction_confidence": 0.95,
          "rationale": "The passage states the launch directly."
        }
      ]
    }
  ]
}
```

Unknown fields are rejected.

## Promotion gates

A result is promoted only when:

1. JSON satisfies the strict schema.
2. Entity local identifiers are unique.
3. Every entity mention points to an existing passage.
4. Mention text exactly matches its passage-relative offsets.
5. Every claim subject resolves to an entity in the same result.
6. Every claim has at least one non-irrelevant evidence link.
7. Every evidence link points to an existing passage.

Invalid results are retained in `model_executions` with their raw output and validation errors. They create no entities, mentions, claims, or UEOs.

## Idempotency

The input hash contains the document hash, ordered passage hashes, and prompt version. A successful repeat with the same provider, model, prompt, and input returns the prior execution without calling the provider again.

## Human review

An analyst can set an extracted claim to `accepted`, `rejected`, or `needs_review`. Each decision appends a `review_decisions` record with reason, actor, and timestamp. The original extraction remains unchanged.
