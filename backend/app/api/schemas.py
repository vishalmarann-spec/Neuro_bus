from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.core.models import (
    ClaimReviewStatus,
    ClusterLabel,
    ConnectorJobStatus,
    DocumentProvenanceRelation,
    EntityType,
    EvidenceStance,
    InsightStatus,
    QuestionStatus,
    RunState,
    SourceType,
    ValidationStatus,
)
from app.evaluation.models import GoldCase
from app.evaluation.review import (
    RESERVED_NON_HUMAN_REVIEWERS,
    GoldReviewRecord,
    ReviewChecklist,
    ReviewDecision,
)
from app.services.evaluation_review import BenchmarkReviewState


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    vertical: str = Field(default="university", min_length=1, max_length=80)

    @field_validator("name", "vertical")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProjectRead(APIModel):
    id: UUID
    name: str
    vertical: str
    created_at: datetime


class QuestionCreate(APIModel):
    text: str = Field(min_length=3)
    scope: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class QuestionRead(APIModel):
    id: UUID
    project_id: UUID
    text: str
    scope: dict[str, Any]
    status: QuestionStatus
    created_at: datetime


class RunCreate(APIModel):
    pipeline_version: str = Field(default="storage.v1", min_length=1, max_length=64)


class RunRead(APIModel):
    id: UUID
    question_id: UUID
    state: RunState
    pipeline_version: str
    metrics: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DocumentCapture(APIModel):
    url: HttpUrl
    publisher: str = Field(min_length=1, max_length=255)
    publisher_family: str | None = Field(default=None, min_length=1, max_length=255)
    source_type: SourceType = SourceType.OTHER
    title: str | None = Field(default=None, max_length=500)
    raw_content: str = Field(min_length=1)
    published_at: datetime | None = None

    @field_validator("publisher", "raw_content")
    @classmethod
    def preserve_content_but_reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @field_validator("publisher_family")
    @classmethod
    def normalize_optional_publisher_family(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("publisher_family cannot be blank")
        return normalized


class SourceRead(APIModel):
    id: UUID
    canonical_domain: str
    publisher: str
    publisher_family: str | None
    source_type: SourceType
    trust_profile: dict[str, Any]
    created_at: datetime


class PassageRead(APIModel):
    id: UUID
    document_id: UUID
    ordinal: int
    start_offset: int
    end_offset: int
    exact_text: str
    text_hash: str


class DocumentRead(APIModel):
    id: UUID
    run_id: UUID
    source_id: UUID
    original_url: str
    canonical_url: str
    title: str | None
    content_hash: str
    retrieved_at: datetime
    published_at: datetime | None
    parser_version: str


class DocumentCaptureRead(APIModel):
    source: SourceRead
    document: DocumentRead
    passages: list[PassageRead]
    duplicate: bool


class WebSourceFetchCreate(APIModel):
    url: HttpUrl
    publisher: str = Field(min_length=1, max_length=255)
    publisher_family: str | None = Field(default=None, min_length=1, max_length=255)
    source_type: SourceType = SourceType.OTHER
    title: str | None = Field(default=None, max_length=500)
    published_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def reject_url_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username or value.password:
            raise ValueError("url must not contain credentials")
        return value

    @field_validator("publisher")
    @classmethod
    def strip_publisher(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("publisher cannot be blank")
        return normalized

    @field_validator("publisher_family")
    @classmethod
    def strip_optional_publisher_family(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("publisher_family cannot be blank")
        return normalized


class ConnectorJobRead(APIModel):
    id: UUID
    run_id: UUID
    document_id: UUID | None
    connector: str
    requested_url: str
    status: ConnectorJobStatus
    attempts: int
    max_attempts: int
    robots_url: str | None
    robots_allowed: bool | None
    final_url: str | None
    response_media_type: str | None
    response_hash: str | None
    response_bytes: int | None
    redirect_count: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class WebSourceFetchRead(APIModel):
    job: ConnectorJobRead
    capture: DocumentCaptureRead | None = None


class DocumentProvenanceLinkCreate(APIModel):
    relation: DocumentProvenanceRelation
    upstream_url: HttpUrl
    rationale: str = Field(min_length=3, max_length=2_000)
    actor: str = Field(default="local_analyst", min_length=1, max_length=160)

    @field_validator("rationale", "actor")
    @classmethod
    def strip_provenance_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized


class DocumentProvenanceLinkRead(APIModel):
    id: UUID
    document_id: UUID
    relation: DocumentProvenanceRelation
    upstream_url: str
    upstream_domain: str
    rationale: str
    actor: str
    created_at: datetime


class DocumentProvenanceLinkCaptureRead(APIModel):
    link: DocumentProvenanceLinkRead
    duplicate: bool


class ExtractionRunRead(APIModel):
    execution_id: UUID
    status: ValidationStatus
    entities_count: int = 0
    claims_count: int = 0
    evidence_links_count: int = 0
    idempotent: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class ModelExecutionRead(APIModel):
    id: UUID
    run_id: UUID
    document_id: UUID
    task: str
    provider: str
    model: str
    prompt_version: str
    input_hash: str
    raw_output: str | None
    validation_status: ValidationStatus
    validation_errors: list[str]
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    created_at: datetime


class UEOEntityRead(APIModel):
    id: UUID
    entity_type: EntityType
    canonical_name: str


class UEOClaimRead(APIModel):
    id: UUID
    normalized_text: str
    subject: UEOEntityRead | None
    predicate: str
    object_value: dict[str, Any]
    qualifiers: dict[str, Any]
    extraction_confidence: float
    review_status: ClaimReviewStatus


class UEOEvidenceRead(APIModel):
    link_id: UUID
    stance: EvidenceStance
    passage_id: UUID
    quote: str
    directness: float
    extraction_confidence: float
    rationale: str


class UEOProvenanceRead(APIModel):
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    document_hash: str


class UEOScoresRead(APIModel):
    source_trust: float | None = None
    evidence_quality: float | None = None
    extraction_confidence: float


class UEOVersionsRead(APIModel):
    schema_version: str = "ueo.v1"
    extractor_version: str
    scoring_version: str | None = None


class UEORead(APIModel):
    id: str
    claim: UEOClaimRead
    evidence: UEOEvidenceRead
    provenance: UEOProvenanceRead
    scores: UEOScoresRead
    versions: UEOVersionsRead


class ClaimReviewCreate(APIModel):
    action: ClaimReviewStatus
    reason: str = Field(min_length=3)
    actor: str = Field(default="local_analyst", min_length=1, max_length=160)

    @field_validator("action")
    @classmethod
    def validate_review_action(cls, value: ClaimReviewStatus) -> ClaimReviewStatus:
        allowed = {
            ClaimReviewStatus.ACCEPTED,
            ClaimReviewStatus.REJECTED,
            ClaimReviewStatus.NEEDS_REVIEW,
        }
        if value not in allowed:
            raise ValueError("action must be accepted, rejected, or needs_review")
        return value

    @field_validator("reason", "actor")
    @classmethod
    def strip_review_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized


class ClaimReviewRead(APIModel):
    decision_id: UUID
    claim_id: UUID
    action: ClaimReviewStatus
    reason: str
    actor: str
    created_at: datetime


class ClaimClusterScoreRead(APIModel):
    cluster_id: UUID
    canonical_text: str
    predicate: str
    support_strength: float
    contradiction_strength: float
    confidence: float
    label: ClusterLabel
    supporting_independent_sources: int
    evidence_count: int
    scoring_version: str
    explanation: dict[str, Any]
    calculated_at: datetime


class ReasoningRunRead(APIModel):
    run_id: UUID
    clusters: list[ClaimClusterScoreRead]


class InsightRead(APIModel):
    id: UUID
    run_id: UUID
    title: str
    conclusion: str
    confidence: float
    status: InsightStatus
    generation_version: str
    fingerprint: str
    explanation: dict[str, Any]
    created_at: datetime


class InsightGenerationRead(InsightRead):
    idempotent: bool


class InsightCitationRead(APIModel):
    evidence_link_id: UUID
    stance: EvidenceStance
    passage_id: UUID
    quote: str
    canonical_url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    document_hash: str
    evidence_quality: float | None


class InsightStatementRead(APIModel):
    id: UUID
    cluster_id: UUID | None
    claim_id: UUID | None
    text: str
    label: ClusterLabel
    confidence: float
    display_order: int
    citations: list[InsightCitationRead]


class InsightReportRead(APIModel):
    insight: InsightRead
    statements: list[InsightStatementRead]


class BenchmarkReviewCaseRead(APIModel):
    case: GoldCase
    case_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    state: BenchmarkReviewState
    latest_review: GoldReviewRecord | None


class BenchmarkReviewSummaryRead(APIModel):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    approved: int = Field(ge=0)
    changes_requested: int = Field(ge=0)
    rejected: int = Field(ge=0)
    stale: int = Field(ge=0)


class BenchmarkReviewQueueRead(APIModel):
    summary: BenchmarkReviewSummaryRead
    cases: list[BenchmarkReviewCaseRead]


class BenchmarkReviewDecisionCreate(APIModel):
    case_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reviewer: str = Field(min_length=2, max_length=160)
    decision: ReviewDecision
    checklist: ReviewChecklist
    notes: str = Field(min_length=3, max_length=2_000)

    @field_validator("reviewer")
    @classmethod
    def validate_human_reviewer(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized.casefold() in RESERVED_NON_HUMAN_REVIEWERS:
            raise ValueError("reviewer must identify the human who performed the review")
        return normalized

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("notes cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_approval_checklist(self) -> "BenchmarkReviewDecisionCreate":
        if self.decision == "approved" and not self.checklist.complete:
            raise ValueError("Approved reviews require every checklist item to be confirmed.")
        return self
