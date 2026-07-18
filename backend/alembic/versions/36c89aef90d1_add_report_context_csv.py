"""add report context csv and full scoring columns

Revision ID: 36c89aef90d1
Revises: e7f839a2d104
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "36c89aef90d1"
down_revision: str | Sequence[str] | None = "e7f839a2d104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("context_csv_path", sa.String(length=500), nullable=True))
    op.add_column("anomalies", sa.Column("score_isolation_forest", sa.Float(), nullable=True))
    op.add_column("anomalies", sa.Column("score_isolation_forest_norm", sa.Float(), nullable=True))
    op.add_column("anomalies", sa.Column("rank_isolation_forest", sa.Integer(), nullable=True))
    op.add_column("anomalies", sa.Column("score_lof", sa.Float(), nullable=True))
    op.add_column("anomalies", sa.Column("score_lof_norm", sa.Float(), nullable=True))
    op.add_column("anomalies", sa.Column("rank_lof", sa.Integer(), nullable=True))
    op.add_column("anomalies", sa.Column("score_combined", sa.Float(), nullable=True))
    op.add_column("anomalies", sa.Column("rank_combined", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("anomalies", "rank_combined")
    op.drop_column("anomalies", "score_combined")
    op.drop_column("anomalies", "rank_lof")
    op.drop_column("anomalies", "score_lof_norm")
    op.drop_column("anomalies", "score_lof")
    op.drop_column("anomalies", "rank_isolation_forest")
    op.drop_column("anomalies", "score_isolation_forest_norm")
    op.drop_column("anomalies", "score_isolation_forest")
    op.drop_column("reports", "context_csv_path")
