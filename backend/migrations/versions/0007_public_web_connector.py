"""Add auditable public web connector jobs.

Revision ID: 0007_public_web_connector
Revises: 0006_source_independence
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_public_web_connector"
down_revision: str | None = "0006_source_independence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

connector_job_status = sa.Enum(
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "BLOCKED",
    "UNAVAILABLE",
    name="connectorjobstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "connector_jobs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("connector", sa.String(length=64), nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("status", connector_job_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("robots_url", sa.Text(), nullable=True),
        sa.Column("robots_allowed", sa.Boolean(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("response_media_type", sa.String(length=120), nullable=True),
        sa.Column("response_hash", sa.String(length=71), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("redirect_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_connector_job_attempts_nonnegative"),
        sa.CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 5",
            name="ck_connector_job_max_attempts",
        ),
        sa.CheckConstraint(
            "response_bytes IS NULL OR response_bytes >= 0",
            name="ck_connector_job_response_bytes_nonnegative",
        ),
        sa.CheckConstraint(
            "redirect_count IS NULL OR redirect_count >= 0",
            name="ck_connector_job_redirect_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connector_jobs_document_id", "connector_jobs", ["document_id"])
    op.create_index("ix_connector_jobs_error_code", "connector_jobs", ["error_code"])
    op.create_index("ix_connector_jobs_response_hash", "connector_jobs", ["response_hash"])
    op.create_index("ix_connector_jobs_run_id", "connector_jobs", ["run_id"])
    op.create_index("ix_connector_jobs_status", "connector_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_connector_jobs_status", table_name="connector_jobs")
    op.drop_index("ix_connector_jobs_run_id", table_name="connector_jobs")
    op.drop_index("ix_connector_jobs_response_hash", table_name="connector_jobs")
    op.drop_index("ix_connector_jobs_error_code", table_name="connector_jobs")
    op.drop_index("ix_connector_jobs_document_id", table_name="connector_jobs")
    op.drop_table("connector_jobs")
