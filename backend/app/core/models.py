from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class QuestionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RunState(StrEnum):
    QUEUED = "queued"
    COLLECTING = "collecting"
    COMPLETED = "completed"
    COMPLETED_PARTIAL = "completed_partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceType(StrEnum):
    UNIVERSITY = "university"
    GOVERNMENT = "government"
    RESEARCH = "research"
    NEWS = "news"
    INDUSTRY = "industry"
    DISCUSSION = "discussion"
    OTHER = "other"


class EntityType(StrEnum):
    UNIVERSITY = "university"
    PROGRAMME = "programme"
    COURSE = "course"
    SKILL = "skill"
    TECHNOLOGY = "technology"
    EMPLOYER = "employer"
    INDUSTRY = "industry"
    LOCATION = "location"
    CREDENTIAL = "credential"
    PRICE = "price"
    DATE = "date"
    METRIC = "metric"
    ORGANIZATION = "organization"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUAL = "contextual"
    IRRELEVANT = "irrelevant"


class ClaimReviewStatus(StrEnum):
    MACHINE_EXTRACTED = "machine_extracted"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ValidationStatus(StrEnum):
    ACCEPTED = "accepted"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class ClusterLabel(StrEnum):
    WELL_SUPPORTED = "well_supported"
    SUPPORTED = "supported"
    EMERGING = "emerging"
    WEAK = "weak"
    DISPUTED = "disputed"


class InsightStatus(StrEnum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"


class Project(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    vertical: Mapped[str] = mapped_column(String(80), nullable=False, default="university")

    questions: Mapped[list["ResearchQuestion"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ResearchQuestion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "research_questions"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(QuestionStatus, native_enum=False, length=32),
        nullable=False,
        default=QuestionStatus.DRAFT,
    )

    project: Mapped[Project] = relationship(back_populates="questions")
    runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class AnalysisRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "analysis_runs"

    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[RunState] = mapped_column(
        Enum(RunState, native_enum=False, length=32),
        nullable=False,
        default=RunState.QUEUED,
    )
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False, default="storage.v1")
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    question: Mapped[ResearchQuestion] = relationship(back_populates="runs")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Source(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("canonical_domain", "publisher", "source_type", name="uq_source_identity"),
    )

    canonical_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=32), nullable=False
    )
    trust_profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    documents: Mapped[list["Document"]] = relationship(back_populates="source")


class Document(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("run_id", "canonical_url", "content_hash", name="uq_document_capture"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False, default="text.v1")

    run: Mapped[AnalysisRun] = relationship(back_populates="documents")
    source: Mapped[Source] = relationship(back_populates="documents")
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Passage.ordinal",
    )
    model_executions: Mapped[list["ModelExecution"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Passage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "passages"
    __table_args__ = (UniqueConstraint("document_id", "ordinal", name="uq_passage_ordinal"),)

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    exact_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    document: Mapped[Document] = relationship(back_populates="passages")
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan"
    )
    evidence_links: Mapped[list["EvidenceLink"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan"
    )


class ModelExecution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "model_executions"

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    raw_output: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus, native_enum=False, length=32), nullable=False
    )
    validation_errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)

    document: Mapped[Document] = relationship(back_populates="model_executions")
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="model_execution", cascade="all, delete-orphan"
    )
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        back_populates="model_execution", cascade="all, delete-orphan"
    )


class Entity(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_name", name="uq_entity_identity"),
    )

    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, native_enum=False, length=32), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    mentions: Mapped[list["EntityMention"]] = relationship(back_populates="entity")
    subject_claims: Mapped[list["Claim"]] = relationship(back_populates="subject_entity")


class EntityMention(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mention_confidence"),
    )

    entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    passage_id: Mapped[UUID] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    surface_text: Mapped[str] = mapped_column(String(500), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    entity: Mapped[Entity] = relationship(back_populates="mentions")
    passage: Mapped[Passage] = relationship(back_populates="entity_mentions")
    model_execution: Mapped[ModelExecution] = relationship(back_populates="entity_mentions")


class Claim(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "extraction_confidence >= 0 AND extraction_confidence <= 1",
            name="ck_claim_extraction_confidence",
        ),
    )

    model_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("claim_clusters.id", ondelete="SET NULL"), index=True
    )
    subject_entity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), index=True
    )
    predicate: Mapped[str] = mapped_column(String(160), nullable=False)
    object_value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    qualifiers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[ClaimReviewStatus] = mapped_column(
        Enum(ClaimReviewStatus, native_enum=False, length=32),
        nullable=False,
        default=ClaimReviewStatus.MACHINE_EXTRACTED,
    )

    model_execution: Mapped[ModelExecution] = relationship(back_populates="claims")
    subject_entity: Mapped[Entity | None] = relationship(back_populates="subject_claims")
    evidence_links: Mapped[list["EvidenceLink"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    cluster: Mapped["ClaimCluster | None"] = relationship(back_populates="claims")


class EvidenceLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        CheckConstraint("directness >= 0 AND directness <= 1", name="ck_evidence_directness"),
        CheckConstraint(
            "extraction_confidence >= 0 AND extraction_confidence <= 1",
            name="ck_evidence_extraction_confidence",
        ),
    )

    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    passage_id: Mapped[UUID] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stance: Mapped[EvidenceStance] = mapped_column(
        Enum(EvidenceStance, native_enum=False, length=32), nullable=False
    )
    directness: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float)
    quality_components: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    claim: Mapped[Claim] = relationship(back_populates="evidence_links")
    passage: Mapped[Passage] = relationship(back_populates="evidence_links")


class ReviewDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "review_decisions"

    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[ClaimReviewStatus] = mapped_column(
        Enum(ClaimReviewStatus, native_enum=False, length=32), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(160), nullable=False, default="local_analyst")

    claim: Mapped[Claim] = relationship(back_populates="review_decisions")


class ClaimCluster(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "claim_clusters"
    __table_args__ = (UniqueConstraint("run_id", "cluster_key", name="uq_run_claim_cluster"),)

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_key: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    subject_entity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), index=True
    )
    predicate: Mapped[str] = mapped_column(String(160), nullable=False)
    object_signature: Mapped[str] = mapped_column(Text, nullable=False)
    qualifiers_signature: Mapped[str] = mapped_column(Text, nullable=False)

    claims: Mapped[list[Claim]] = relationship(back_populates="cluster")
    score: Mapped["ClaimClusterScore | None"] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", uselist=False
    )


class ClaimClusterScore(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "claim_cluster_scores"
    __table_args__ = (
        CheckConstraint(
            "support_strength >= 0 AND support_strength <= 1",
            name="ck_cluster_support_strength",
        ),
        CheckConstraint(
            "contradiction_strength >= 0 AND contradiction_strength <= 1",
            name="ck_cluster_contradiction_strength",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_cluster_confidence"),
    )

    cluster_id: Mapped[UUID] = mapped_column(
        ForeignKey("claim_clusters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    support_strength: Mapped[float] = mapped_column(Float, nullable=False)
    contradiction_strength: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[ClusterLabel] = mapped_column(
        Enum(ClusterLabel, native_enum=False, length=32), nullable=False
    )
    supporting_independent_sources: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    cluster: Mapped[ClaimCluster] = relationship(back_populates="score")


class Insight(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "insights"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_insight_confidence"),
        UniqueConstraint("run_id", "fingerprint", name="uq_run_insight_fingerprint"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[InsightStatus] = mapped_column(
        Enum(InsightStatus, native_enum=False, length=32), nullable=False
    )
    generation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    explanation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    run: Mapped[AnalysisRun] = relationship(back_populates="insights")
    statements: Mapped[list["InsightStatement"]] = relationship(
        back_populates="insight",
        cascade="all, delete-orphan",
        order_by="InsightStatement.display_order",
    )


class InsightStatement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "insight_statements"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_insight_statement_confidence"
        ),
        UniqueConstraint("insight_id", "display_order", name="uq_insight_statement_order"),
    )

    insight_id: Mapped[UUID] = mapped_column(
        ForeignKey("insights.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("claim_clusters.id", ondelete="SET NULL"), index=True
    )
    claim_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[ClusterLabel] = mapped_column(
        Enum(ClusterLabel, native_enum=False, length=32), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    insight: Mapped[Insight] = relationship(back_populates="statements")
    citations: Mapped[list["InsightCitation"]] = relationship(
        back_populates="statement",
        cascade="all, delete-orphan",
        order_by="InsightCitation.display_order",
    )


class InsightCitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "insight_citations"
    __table_args__ = (
        UniqueConstraint("statement_id", "evidence_link_id", name="uq_statement_evidence_citation"),
        UniqueConstraint("statement_id", "display_order", name="uq_statement_citation_order"),
    )

    statement_id: Mapped[UUID] = mapped_column(
        ForeignKey("insight_statements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_link_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_links.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    statement: Mapped[InsightStatement] = relationship(back_populates="citations")
