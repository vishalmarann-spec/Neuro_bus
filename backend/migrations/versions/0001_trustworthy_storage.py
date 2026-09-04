"""Create trustworthy storage foundation.

Revision ID: 0001_trustworthy_storage
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_trustworthy_storage"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

question_status = sa.Enum("DRAFT", "ACTIVE", "ARCHIVED", name="questionstatus", native_enum=False)
run_state = sa.Enum(
    "QUEUED",
    "COLLECTING",
    "COMPLETED",
    "COMPLETED_PARTIAL",
    "FAILED",
    "CANCELLED",
    name="runstate",
    native_enum=False,
)
source_type = sa.Enum(
    "UNIVERSITY",
    "GOVERNMENT",
    "RESEARCH",
    "NEWS",
    "INDUSTRY",
    "DISCUSSION",
    "OTHER",
    name="sourcetype",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("vertical", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sources",
        sa.Column("canonical_domain", sa.String(length=255), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("trust_profile", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_domain", "publisher", "source_type", name="uq_source_identity"
        ),
    )
    op.create_index("ix_sources_canonical_domain", "sources", ["canonical_domain"])
    op.create_table(
        "research_questions",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", question_status, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_questions_project_id", "research_questions", ["project_id"])
    op.create_table(
        "analysis_runs",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("state", run_state, nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["research_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_question_id", "analysis_runs", ["question_id"])
    op.create_table(
        "documents",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "canonical_url", "content_hash", name="uq_document_capture"),
    )
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index("ix_documents_run_id", "documents", ["run_id"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_table(
        "passages",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("exact_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=71), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_passage_ordinal"),
    )
    op.create_index("ix_passages_document_id", "passages", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_passages_document_id", table_name="passages")
    op.drop_table("passages")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_index("ix_documents_run_id", table_name="documents")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_analysis_runs_question_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_index("ix_research_questions_project_id", table_name="research_questions")
    op.drop_table("research_questions")
    op.drop_index("ix_sources_canonical_domain", table_name="sources")
    op.drop_table("sources")
    op.drop_table("projects")
