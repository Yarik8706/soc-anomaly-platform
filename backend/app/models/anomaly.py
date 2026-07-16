import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity: Mapped[str] = mapped_column(String(255), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )

    explanations: Mapped[list["AnomalyExplanation"]] = relationship(
        back_populates="anomaly", cascade="all, delete-orphan"
    )


class AnomalyExplanation(Base):
    __tablename__ = "anomaly_explanations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    anomaly_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anomalies.id", ondelete="CASCADE"), index=True
    )
    feature_name: Mapped[str] = mapped_column(String(255))
    feature_value: Mapped[float] = mapped_column(Float)
    baseline_value: Mapped[float] = mapped_column(Float)
    contribution: Mapped[float] = mapped_column(Float)

    anomaly: Mapped[Anomaly] = relationship(back_populates="explanations")
