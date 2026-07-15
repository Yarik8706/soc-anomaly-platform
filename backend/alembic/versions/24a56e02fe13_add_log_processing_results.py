"""add log processing results

Revision ID: 24a56e02fe13
Revises: 2f04b3f439f0
Create Date: 2026-07-15 21:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "24a56e02fe13"
down_revision: str | Sequence[str] | None = "2f04b3f439f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "uploaded_files",
        sa.Column("validation_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("validated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("normalization_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("normalized_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("uploaded_files", "normalized_at")
    op.drop_column("uploaded_files", "normalization_result")
    op.drop_column("uploaded_files", "validated_at")
    op.drop_column("uploaded_files", "validation_result")
