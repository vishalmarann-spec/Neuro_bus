# Execution board

## Tonight: planning and foundation

- [x] Lock university intelligence as the first vertical.
- [x] Define MVP/non-goals and measurable success criteria.
- [x] Choose modular-monolith architecture and stack.
- [x] Define evidence/domain records and UEO v1.
- [x] Define scoring, independence, and reasoning rules.
- [x] Define API surface and failure envelope.
- [x] Define security and audit boundaries.
- [x] Create repository structure and local dependency configuration.
- [x] Run backend quality checks and tests.
- [x] Authenticate/connect the target GitHub repository.

## Milestone 1: trustworthy storage

Goal: persist a manually submitted source and exact passages with immutable provenance.

- [x] SQLAlchemy models and Alembic baseline
- [x] Project/question/run APIs
- [x] Source/document/passage repositories
- [x] Content hashing and URL canonicalization
- [x] Unit and integration tests
- [ ] Run the migration and integration suite against PostgreSQL/pgvector (Docker is not available in the current Codex runtime).

Exit: restart-safe document/passages with verified hashes and no model dependency. The SQLite integration and migration-reversibility gates pass; the production PostgreSQL gate remains before deployment.

## Milestone 2: one-source extraction

Goal: convert one captured document into schema-valid claim candidates and UEOs.

- [x] Parser and passage segmentation
- [x] Model provider interface and disabled/fake provider
- [x] Structured entity/claim extraction
- [x] Provenance validator
- [x] Model execution log and invalid-output quarantine
- [x] Append-only claim review API
- [x] Traceable UEO API
- [ ] Select and configure a real model-provider adapter after evaluating extraction quality/cost.

Exit: every accepted claim cites an exact stored passage; invalid model output is quarantined. The deterministic provider-independent path meets this gate; live-model selection remains an explicit integration decision.

## Model evaluation checkpoint

- [x] Versioned benchmark schemas and file loaders
- [x] Synthetic smoke set with no fabricated URLs
- [x] Provider benchmark runner
- [x] Entity, mention, claim, evidence, validity, latency, token, and cost metrics
- [x] Model usage metadata in audit records
- [x] Offline comparison CLI
- [x] Curate a 10-case assistant-verified public-source pilot with integrity checks
- [x] Expand to 20 assistant-verified public cases with task/difficulty coverage labels
- [x] Expand to 40 assistant-verified public cases across admissions, accreditation, employer demand, research methods, and negative controls
- [x] Add deterministic coverage audit and selection-grade diversity gates
- [x] Fingerprint-bound append-only human-review ledger and CLI
- [x] Local benchmark human-review API and responsive workspace
- [x] Deterministic 60/20/20 split manifest with 100-case and human-review gates
- [ ] Obtain human sign-off for the public-source pilot
- [ ] Curate the real, reviewable university-domain evaluation set
- [ ] Run candidate models and select the production adapter

## Milestone 3: multi-source reasoning

Goal: combine at least five documents from three independent domains.

- [x] Conservative exact-name and exact-alias entity resolution
- [x] Deterministic claim normalization and clustering
- [x] Exact-content duplicate detection and same-publisher grouping
- [ ] Upstream citation and publisher-family detection
- [x] Support/contradiction aggregation
- [x] Versioned, deterministic score explanations
- [x] Disputed-cluster API for conflict review
- [x] Idempotent reasoning reruns
- [ ] Validate supported, disputed, and weak labels on the real labelled set

Exit: the demo topic produces supported, disputed, and weak claims correctly on a labelled sample.

## Milestone 4: cited insight report

Goal: generate an analyst-ready output without unsupported prose.

- [x] Deterministic evidence retrieval rules
- [x] Constrained synthesis from stored normalized claims only
- [x] Sentence-level citation validation
- [x] Derived insight confidence and rationale
- [x] Immutable, idempotent report persistence and APIs
- [x] Explicit reasoning-required and insufficient-evidence failures
- [ ] Optional model-written narrative behind the same citation validator
- [x] Deterministic Markdown report export
- [x] Responsive analyst report UI with loading, empty, and failure states
- [x] Print-ready report presentation
- [ ] Validate citation correctness >= 0.95 on the real evaluation set

Exit: citation correctness >= 0.95 on the evaluation set.

## Milestone 5: demo hardening

- end-to-end observability
- retry/idempotency tests
- source policy and SSRF safeguards
- accessibility and responsive UI
- deployment, backups, and demo fixtures
- evaluation report

## Deferred backlog

- YouTube transcript connector
- Reddit connector
- private enterprise connectors
- continuous monitoring/alerts
- forecasting
- Neo4j
- multi-tenant billing and permissions

## Working method with Codex

For each vertical slice:

1. Restate acceptance criteria.
2. Inspect existing code and tests.
3. Implement the smallest complete slice.
4. Run formatting, static checks, unit tests, and integration tests.
5. Summarize changed files, risks, and the next checkpoint.

Do not ask Codex to "build the whole platform" in one prompt. Work from this board milestone by milestone.
