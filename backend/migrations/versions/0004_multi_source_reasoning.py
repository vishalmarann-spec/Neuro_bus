"""Add multi-source claim clusters and scores.

Revision ID: 0004_multi_source_reasoning
Revises: 0003_model_usage_metrics
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_multi_source_reasoning"
down_revision: str | None = "0003_model_usage_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

cluster_label = sa.Enum(
    "WELL_SUPPORTED",
    "SUPPORTED",
    "EMERGING",
    "WEAK",
    "DISPUTED",
    name="clusterlabel",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "claim_clusters",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("cluster_key", sa.String(length=71), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=True),
        sa.Column("predicate", sa.String(length=160), nullable=False),
        sa.Column("object_signature", sa.Text(), nullable=False),
        sa.Column("qualifiers_signature", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "cluster_key", name="uq_run_claim_cluster"),
    )
    op.create_index("ix_claim_clusters_run_id", "claim_clusters", ["run_id"])
    op.create_index("ix_claim_clusters_subject_entity_id", "claim_clusters", ["subject_entity_id"])

    with op.batch_alter_table("claims") as batch_op:
        batch_op.add_column(sa.Column("cluster_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_claims_cluster_id_claim_clusters",
            "claim_clusters",
            ["cluster_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_claims_cluster_id", ["cluster_id"])

    op.add_column("evidence_links", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column(
        "evidence_links",
        sa.Column("quality_components", sa.JSON(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "claim_cluster_scores",
        sa.Column("cluster_id", sa.Uuid(), nullable=False),
        sa.Column("support_strength", sa.Float(), nullable=False),
        sa.Column("contradiction_strength", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("label", cluster_label, nullable=False),
        sa.Column("supporting_independent_sources", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("scoring_version", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_cluster_confidence"),
        sa.CheckConstraint(
            "contradiction_strength >= 0 AND contradiction_strength <= 1",
            name="ck_cluster_contradiction_strength",
        ),
        sa.CheckConstraint(
            "support_strength >= 0 AND support_strength <= 1",
            name="ck_cluster_support_strength",
        ),
        sa.ForeignKeyConstraint(["cluster_id"], ["claim_clusters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cluster_id"),
    )
    op.create_index("ix_claim_cluster_scores_cluster_id", "claim_cluster_scores", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_claim_cluster_scores_cluster_id", table_name="claim_cluster_scores")
    op.drop_table("claim_cluster_scores")
    op.drop_column("evidence_links", "quality_components")
    op.drop_column("evidence_links", "quality_score")
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_index("ix_claims_cluster_id")
        batch_op.drop_constraint("fk_claims_cluster_id_claim_clusters", type_="foreignkey")
        batch_op.drop_column("cluster_id")
    op.drop_index("ix_claim_clusters_subject_entity_id", table_name="claim_clusters")
    op.drop_index("ix_claim_clusters_run_id", table_name="claim_clusters")
    op.drop_table("claim_clusters")
