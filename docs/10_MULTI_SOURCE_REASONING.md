# Multi-source reasoning v2

## Implemented pipeline

`POST /api/v1/runs/{run_id}/reason` reads only claims from accepted model executions and excludes analyst-rejected claims. It then:

1. resolves subjects conservatively by exact normalized name or one unambiguous exact alias;
2. constructs a stable cluster key from entity type/name, predicate, canonical JSON object, and qualifiers;
3. calculates source trust, specificity, claim-type freshness, and evidence quality;
4. assigns a transitive independence group from exact content, normalized source identity, declared publisher family, and explicit upstream provenance links;
5. aggregates support and contradiction with the versioned rules in `03_SCORING_AND_REASONING.md`;
6. persists the cluster score and a contribution-level explanation.

Repeating the operation updates the existing score instead of creating a duplicate cluster or score. If review decisions make a previously scored cluster empty, recomputation removes that stale derived cluster and detaches excluded claims.

## Independence boundary

The implementation detects four reviewable forms of dependence:

- documents with the same immutable content hash share a `content:` group, even across domains;
- evidence from the same normalized source record shares a `source:` group;
- sources with the same explicitly declared, case-insensitive publisher family share a `publisher-family:` group;
- documents with a provenance link to the same canonical upstream URL share an `upstream:` group.

Dependence is transitive across these signals. Within a stance/group, the strongest item has full weight and later items have `0.25` weight. Every contribution exposes both the selected group and all shared reasons. The system deliberately does not guess publisher ownership, syndication, or study identity from prose: an analyst or trusted connector must declare publisher-family metadata and record `upstream_study` or `syndicated_from` links with an actor and rationale.

The scoring identifier is `claim-confidence.v2`. Reasoning metrics record the number of independence groups, explicit dependency links, and declared publisher families used in a run.

## Provenance APIs

- `POST /api/v1/documents/{document_id}/provenance-links` records an idempotent, canonicalized upstream relationship.
- `GET /api/v1/documents/{document_id}/provenance-links` returns the stored actor, rationale, relationship, canonical URL, and timestamp.
- `POST /api/v1/runs/{run_id}/sources` accepts optional `publisher_family` metadata and rejects a conflicting declaration for an existing source.

## Missing and malformed score inputs

Missing source-trust components are excluded from the weighted denominator and listed in the stored explanation. Unsupported values, booleans, NaN, and infinity are treated as missing. If every source-trust component is missing, source trust is also omitted from evidence quality rather than silently using the neutral fallback as known evidence.

## API outputs

- `GET /api/v1/runs/{run_id}/clusters` returns every persisted scored cluster.
- `GET /api/v1/runs/{run_id}/conflicts` returns only clusters labelled `disputed`.

Every result exposes support strength, contradiction strength, confidence, label, independent-support count, evidence count, scoring version, calculation time, and each evidence contribution.

## Validation boundary

Synthetic tests cover independent corroboration, exact-copy discounting, publisher-family grouping, shared upstream-study grouping, transitive dependencies, contradiction, freshness, missing inputs, conservative alias handling, API output, and idempotency. The milestone exit condition remains open until these rules produce the expected supported, disputed, and weak labels on the curated real evaluation set.
