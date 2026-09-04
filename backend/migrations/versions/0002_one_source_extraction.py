"""Add one-source evidence extraction records.

Revision ID: 0002_one_source_extraction
Revises: 0001_trustworthy_storage
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_one_source_extraction"
down_revision: str | None = "0001_trustworthy_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

entity_type = sa.Enum(
    "UNIVERSITY",
    "PROGRAMME",
    "COURSE",
    "SKILL",
    "TECHNOLOGY",
    "EMPLOYER",
    "INDUSTRY",
    "LOCATION",
    "CREDENTIAL",
    "PRICE",
    "DATE",
    "METRIC",
    "ORGANIZATION",
    name="entitytype",
    native_enum=False,
)
evidence_stance = sa.Enum(
    "SUPPORTS",
    "CONTRADICTS",
    "CONTEXTUAL",
    "IRRELEVANT",
    name="evidencestance",
    native_enum=False,
)
claim_review_status = sa.Enum(
    "MACHINE_EXTRACTED",
    "ACCEPTED",
    "CORRECTED",
    "REJECTED",
    "NEEDS_REVIEW",
    name="claimreviewstatus",
    native_enum=False,
)
validation_status = sa.Enum(
    "ACCEPTED",
    "INVALID",
    "UNAVAILABLE",
    name="validationstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("entity_type", entity_type, nullable=False),
        sa.Column("canonical_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_name", sa.String(length=500), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "normalized_name", name="uq_entity_identity"),
    )
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])

    op.create_table(
        "model_executions",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("validation_status", validation_status, nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_executions_document_id", "model_executions", ["document_id"])
    op.create_index("ix_model_executions_input_hash", "model_executions", ["input_hash"])
    op.create_index("ix_model_executions_run_id", "model_executions", ["run_id"])

    op.create_table(
        "claims",
        sa.Column("model_execution_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=True),
        sa.Column("predicate", sa.String(length=160), nullable=False),
        sa.Column("object_value", sa.JSON(), nullable=False),
        sa.Column("qualifiers", sa.JSON(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("review_status", claim_review_status, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "extraction_confidence >= 0 AND extraction_confidence <= 1",
            name="ck_claim_extraction_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["model_execution_id"], ["model_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_model_execution_id", "claims", ["model_execution_id"])
    op.create_index("ix_claims_subject_entity_id", "claims", ["subject_entity_id"])

    op.create_table(
        "entity_mentions",
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("model_execution_id", sa.Uuid(), nullable=False),
        sa.Column("surface_text", sa.String(length=500), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mention_confidence"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["model_execution_id"], ["model_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["passage_id"], ["passages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_mentions_entity_id", "entity_mentions", ["entity_id"])
    op.create_index(
        "ix_entity_mentions_model_execution_id", "entity_mentions", ["model_execution_id"]
    )
    op.create_index("ix_entity_mentions_passage_id", "entity_mentions", ["passage_id"])

    op.create_table(
        "evidence_links",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("stance", evidence_stance, nullable=False),
        sa.Column("directness", sa.Float(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("directness >= 0 AND directness <= 1", name="ck_evidence_directness"),
        sa.CheckConstraint(
            "extraction_confidence >= 0 AND extraction_confidence <= 1",
            name="ck_evidence_extraction_confidence",
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["passage_id"], ["passages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_links_claim_id", "evidence_links", ["claim_id"])
    op.create_index("ix_evidence_links_passage_id", "evidence_links", ["passage_id"])

    op.create_table(
        "review_decisions",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("action", claim_review_status, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_decisions_claim_id", "review_decisions", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_review_decisions_claim_id", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index("ix_evidence_links_passage_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_claim_id", table_name="evidence_links")
    op.drop_table("evidence_links")
    op.drop_index("ix_entity_mentions_passage_id", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_model_execution_id", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_entity_id", table_name="entity_mentions")
    op.drop_table("entity_mentions")
    op.drop_index("ix_claims_subject_entity_id", table_name="claims")
    op.drop_index("ix_claims_model_execution_id", table_name="claims")
    op.drop_table("claims")
    op.drop_index("ix_model_executions_run_id", table_name="model_executions")
    op.drop_index("ix_model_executions_input_hash", table_name="model_executions")
    op.drop_index("ix_model_executions_document_id", table_name="model_executions")
    op.drop_table("model_executions")
    op.drop_index("ix_entities_entity_type", table_name="entities")
    op.drop_table("entities")
