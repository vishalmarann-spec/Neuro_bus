from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
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


class Source(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint(
            "canonical_domain", "publisher", "source_type", name="uq_source_identity"
        ),
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
        UniqueConstraint(
            "run_id", "canonical_url", "content_hash", name="uq_document_capture"
        ),
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
