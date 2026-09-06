"""Add explicit upstream-source and publisher-family provenance.

Revision ID: 0006_source_independence
Revises: 0005_cited_insight_reports
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_source_independence"
down_revision: str | None = "0005_cited_insight_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

provenance_relation = sa.Enum(
    "UPSTREAM_STUDY",
    "SYNDICATED_FROM",
    name="documentprovenancerelation",
    native_enum=False,
)


def upgrade() -> None:
    op.add_column("sources", sa.Column("publisher_family", sa.String(length=255), nullable=True))
    op.create_index("ix_sources_publisher_family", "sources", ["publisher_family"])
    op.create_table(
        "document_provenance_links",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("relation", provenance_relation, nullable=False),
        sa.Column("upstream_url", sa.Text(), nullable=False),
        sa.Column("upstream_domain", sa.String(length=255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "relation",
            "upstream_url",
            name="uq_document_provenance_link",
        ),
    )
    op.create_index(
        "ix_document_provenance_links_document_id",
        "document_provenance_links",
        ["document_id"],
    )
    op.create_index(
        "ix_document_provenance_links_upstream_domain",
        "document_provenance_links",
        ["upstream_domain"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_provenance_links_upstream_domain",
        table_name="document_provenance_links",
    )
    op.drop_index(
        "ix_document_provenance_links_document_id",
        table_name="document_provenance_links",
    )
    op.drop_table("document_provenance_links")
    op.drop_index("ix_sources_publisher_family", table_name="sources")
    op.drop_column("sources", "publisher_family")
