"""Add durable connector worker claims and request payloads.

Revision ID: 0008_connector_worker
Revises: 0007_public_web_connector
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_connector_worker"
down_revision: str | None = "0007_public_web_connector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("connector_jobs") as batch_op:
        batch_op.add_column(sa.Column("publisher", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("publisher_family", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("source_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("title", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("request_hash", sa.String(length=71), nullable=True))
        batch_op.add_column(sa.Column("idempotency_hash", sa.String(length=71), nullable=True))
        batch_op.add_column(
            sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch_op.add_column(sa.Column("lease_owner", sa.String(length=160), nullable=True))
        batch_op.add_column(
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("connector_jobs") as batch_op:
        batch_op.create_check_constraint(
            "ck_connector_job_claim_count_nonnegative", "claim_count >= 0"
        )
        batch_op.create_unique_constraint(
            "uq_connector_job_idempotency",
            ["run_id", "connector", "idempotency_hash"],
        )
        batch_op.create_index("ix_connector_jobs_available_at", ["available_at"])
        batch_op.create_index("ix_connector_jobs_lease_owner", ["lease_owner"])
        batch_op.create_index("ix_connector_jobs_lease_expires_at", ["lease_expires_at"])


def downgrade() -> None:
    with op.batch_alter_table("connector_jobs") as batch_op:
        batch_op.drop_index("ix_connector_jobs_lease_expires_at")
        batch_op.drop_index("ix_connector_jobs_lease_owner")
        batch_op.drop_index("ix_connector_jobs_available_at")
        batch_op.drop_constraint("uq_connector_job_idempotency", type_="unique")
        batch_op.drop_constraint("ck_connector_job_claim_count_nonnegative", type_="check")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("lease_owner")
        batch_op.drop_column("available_at")
        batch_op.drop_column("claim_count")
        batch_op.drop_column("idempotency_hash")
        batch_op.drop_column("request_hash")
        batch_op.drop_column("published_at")
        batch_op.drop_column("title")
        batch_op.drop_column("source_type")
        batch_op.drop_column("publisher_family")
        batch_op.drop_column("publisher")
