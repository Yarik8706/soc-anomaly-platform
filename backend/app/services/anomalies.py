from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.anomaly import Anomaly, AnomalyActivity
from app.schemas.anomalies import AnomalyStatusUpdate


def list_anomalies(
    db: Session,
    *,
    run_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    entity_type: str | None = None,
    severity: str | None = None,
    workflow_status: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Anomaly], int, dict[str, int]]:
    filters = []
    if run_id:
        filters.append(Anomaly.run_id == run_id)
    if date_from:
        filters.append(Anomaly.date >= date_from)
    if date_to:
        filters.append(Anomaly.date <= date_to)
    if entity_type:
        filters.append(Anomaly.entity_type == entity_type)
    if severity:
        filters.append(Anomaly.severity == severity)
    if workflow_status:
        filters.append(Anomaly.status == workflow_status)

    statement = (
        select(Anomaly)
        .where(*filters)
        .order_by(Anomaly.date.desc(), Anomaly.score.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(db.scalars(statement).all())
    total = db.scalar(select(func.count()).select_from(Anomaly).where(*filters)) or 0
    counter_rows = db.execute(
        select(Anomaly.severity, func.count())
        .where(*filters)
        .group_by(Anomaly.severity)
    )
    counters = {str(name): int(count) for name, count in counter_rows}
    counters["total"] = int(total)
    return items, int(total), counters


def get_anomaly(db: Session, anomaly_id: UUID) -> Anomaly | None:
    return db.scalar(
        select(Anomaly)
        .where(Anomaly.id == anomaly_id)
        .options(
            selectinload(Anomaly.explanations),
            selectinload(Anomaly.activities),
        )
    )


def update_anomaly_status(
    db: Session,
    anomaly: Anomaly,
    payload: AnomalyStatusUpdate,
    actor_id: UUID | None = None,
) -> Anomaly:
    previous_status = anomaly.status
    new_status = payload.status.value
    if previous_status == new_status and not payload.comment:
        raise ValueError("Status is already set and no comment was provided")

    anomaly.status = new_status
    anomaly.activities.append(
        AnomalyActivity(
            actor_id=actor_id,
            previous_status=previous_status,
            new_status=new_status,
            comment=payload.comment.strip() if payload.comment else None,
        )
    )
    db.commit()
    return get_anomaly(db, anomaly.id)  # type: ignore[return-value]
