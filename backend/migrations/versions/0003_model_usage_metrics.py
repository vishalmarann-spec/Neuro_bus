"""Add model usage and cost metrics.

Revision ID: 0003_model_usage_metrics
Revises: 0002_one_source_extraction
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_model_usage_metrics"
down_revision: str | None = "0002_one_source_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_executions", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("model_executions", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("model_executions", sa.Column("cost_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_executions", "cost_usd")
    op.drop_column("model_executions", "output_tokens")
    op.drop_column("model_executions", "input_tokens")
