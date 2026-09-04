"""Add deterministic cited insight reports.

Revision ID: 0005_cited_insight_reports
Revises: 0004_multi_source_reasoning
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_cited_insight_reports"
down_revision: str | None = "0004_multi_source_reasoning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

insight_status = sa.Enum(
    "READY",
    "NEEDS_REVIEW",
    name="insightstatus",
    native_enum=False,
)
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
        "insights",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", insight_status, nullable=False),
        sa.Column("generation_version", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=71), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_insight_confidence"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "fingerprint", name="uq_run_insight_fingerprint"),
    )
    op.create_index("ix_insights_run_id", "insights", ["run_id"])

    op.create_table(
        "insight_statements",
        sa.Column("insight_id", sa.Uuid(), nullable=False),
        sa.Column("cluster_id", sa.Uuid(), nullable=True),
        sa.Column("claim_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("label", cluster_label, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_insight_statement_confidence",
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cluster_id"], ["claim_clusters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["insight_id"], ["insights.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("insight_id", "display_order", name="uq_insight_statement_order"),
    )
    op.create_index("ix_insight_statements_claim_id", "insight_statements", ["claim_id"])
    op.create_index("ix_insight_statements_cluster_id", "insight_statements", ["cluster_id"])
    op.create_index("ix_insight_statements_insight_id", "insight_statements", ["insight_id"])

    op.create_table(
        "insight_citations",
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_link_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_link_id"], ["evidence_links.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["statement_id"], ["insight_statements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("statement_id", "display_order", name="uq_statement_citation_order"),
        sa.UniqueConstraint(
            "statement_id", "evidence_link_id", name="uq_statement_evidence_citation"
        ),
    )
    op.create_index(
        "ix_insight_citations_evidence_link_id",
        "insight_citations",
        ["evidence_link_id"],
    )
    op.create_index("ix_insight_citations_statement_id", "insight_citations", ["statement_id"])


def downgrade() -> None:
    op.drop_index("ix_insight_citations_statement_id", table_name="insight_citations")
    op.drop_index("ix_insight_citations_evidence_link_id", table_name="insight_citations")
    op.drop_table("insight_citations")
    op.drop_index("ix_insight_statements_insight_id", table_name="insight_statements")
    op.drop_index("ix_insight_statements_cluster_id", table_name="insight_statements")
    op.drop_index("ix_insight_statements_claim_id", table_name="insight_statements")
    op.drop_table("insight_statements")
    op.drop_index("ix_insights_run_id", table_name="insights")
    op.drop_table("insights")
