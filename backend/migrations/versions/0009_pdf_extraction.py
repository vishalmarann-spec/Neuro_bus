"""Add PDF parsing audit fields to connector jobs.

Revision ID: 0009_pdf_extraction
Revises: 0008_connector_worker
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_pdf_extraction"
down_revision: str | None = "0008_connector_worker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("connector_jobs") as batch_op:
        batch_op.add_column(sa.Column("parser_version", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_page_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("extracted_page_count", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_connector_job_source_page_count_nonnegative",
            "source_page_count IS NULL OR source_page_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_connector_job_extracted_page_count_nonnegative",
            "extracted_page_count IS NULL OR extracted_page_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_connector_job_extracted_pages_within_source",
            "source_page_count IS NULL OR extracted_page_count IS NULL "
            "OR extracted_page_count <= source_page_count",
        )


def downgrade() -> None:
    with op.batch_alter_table("connector_jobs") as batch_op:
        batch_op.drop_constraint("ck_connector_job_extracted_pages_within_source", type_="check")
        batch_op.drop_constraint("ck_connector_job_extracted_page_count_nonnegative", type_="check")
        batch_op.drop_constraint("ck_connector_job_source_page_count_nonnegative", type_="check")
        batch_op.drop_column("extracted_page_count")
        batch_op.drop_column("source_page_count")
        batch_op.drop_column("parser_version")
