"""add reports and metrics

Revision ID: b8400be74299
Revises: 9db8c691a21e
Create Date: 2026-07-16 13:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8400be74299"
down_revision: str | Sequence[str] | None = "9db8c691a21e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("markdown_path", sa.String(500), nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_run_id", "reports", ["run_id"])
    op.create_index("ix_reports_status", "reports", ["status"])

    op.create_table(
        "proxy_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_proxy_metrics_run_id"),
    )
    op.create_index("ix_proxy_metrics_run_id", "proxy_metrics", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_proxy_metrics_run_id", table_name="proxy_metrics")
    op.drop_table("proxy_metrics")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_run_id", table_name="reports")
    op.drop_table("reports")
