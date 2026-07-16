import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    target_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    upload_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    stages: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
