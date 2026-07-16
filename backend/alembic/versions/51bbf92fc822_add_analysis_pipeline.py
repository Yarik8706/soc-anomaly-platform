"""add analysis pipeline

Revision ID: 51bbf92fc822
Revises: 24a56e02fe13
Create Date: 2026-07-16 12:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "51bbf92fc822"
down_revision: str | Sequence[str] | None = "24a56e02fe13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("upload_ids", sa.JSON(), nullable=True))
    op.add_column("analysis_runs", sa.Column("stages", sa.JSON(), nullable=True))
    op.add_column("analysis_runs", sa.Column("artifacts", sa.JSON(), nullable=True))
    op.add_column("analysis_runs", sa.Column("current_stage", sa.String(50), nullable=True))
    op.add_column("analysis_runs", sa.Column("job_id", sa.String(100), nullable=True))
    op.add_column(
        "analysis_runs",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("analysis_runs", sa.Column("started_at", sa.DateTime(), nullable=True))

    op.create_table(
        "anomalies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity", sa.String(255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("run_id", "entity_type", "entity", "date", "severity", "status"):
        op.create_index(f"ix_anomalies_{column}", "anomalies", [column])

    op.create_table(
        "anomaly_explanations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("anomaly_id", sa.UUID(), nullable=False),
        sa.Column("feature_name", sa.String(255), nullable=False),
        sa.Column("feature_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomalies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anomaly_explanations_anomaly_id",
        "anomaly_explanations",
        ["anomaly_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_explanations_anomaly_id", table_name="anomaly_explanations")
    op.drop_table("anomaly_explanations")
    for column in ("status", "severity", "date", "entity", "entity_type", "run_id"):
        op.drop_index(f"ix_anomalies_{column}", table_name="anomalies")
    op.drop_table("anomalies")
    for column in (
        "started_at",
        "attempts",
        "job_id",
        "current_stage",
        "artifacts",
        "stages",
        "upload_ids",
    ):
        op.drop_column("analysis_runs", column)
