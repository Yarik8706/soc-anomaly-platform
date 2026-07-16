"""add anomaly workflow

Revision ID: 9db8c691a21e
Revises: 51bbf92fc822
Create Date: 2026-07-16 13:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9db8c691a21e"
down_revision: str | Sequence[str] | None = "51bbf92fc822"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomaly_activities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("anomaly_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("previous_status", sa.String(30), nullable=False),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomalies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anomaly_activities_anomaly_id",
        "anomaly_activities",
        ["anomaly_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_activities_anomaly_id", table_name="anomaly_activities")
    op.drop_table("anomaly_activities")
