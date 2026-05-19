"""add pipeline_runs table

Revision ID: a1b2c3d4e5f6
Revises: c4acc39a8be2
Create Date: 2026-05-17

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c4acc39a8be2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filings_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filings_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filings_classified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flags_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "total_cost_estimate",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="scheduled"),
    )
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
