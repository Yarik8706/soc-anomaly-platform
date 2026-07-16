from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.user import User
from app.schemas.anomalies import (
    AnomalyDetail,
    AnomalyList,
    AnomalyRead,
    AnomalyStatusUpdate,
)
from app.schemas.auth import UserRole
from app.services.audit import record_audit_event
from app.services.auth import require_roles
from app.services.anomalies import get_anomaly, list_anomalies, update_anomaly_status

router = APIRouter(
    prefix="/anomalies",
    tags=["anomalies"],
    dependencies=[Depends(require_roles(*UserRole))],
)
write_required = require_roles(UserRole.admin, UserRole.analyst)


@router.get("", response_model=AnomalyList)
def get_anomalies(
    run_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    entity_type: Literal["user", "host"] | None = None,
    severity: Literal["critical", "high", "medium", "low"] | None = None,
    workflow_status: Literal[
        "new", "investigating", "incident", "false_positive", "closed"
    ]
    | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> AnomalyList:
    items, total, counters = list_anomalies(
        db,
        run_id=run_id,
        date_from=date_from,
        date_to=date_to,
        entity_type=entity_type,
        severity=severity,
        workflow_status=workflow_status,
        offset=offset,
        limit=limit,
    )
    return AnomalyList(
        items=[AnomalyRead.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
        counters=counters,
    )


@router.get("/{anomaly_id}", response_model=AnomalyDetail)
def get_anomaly_detail(
    anomaly_id: UUID, db: Session = Depends(get_db)
) -> AnomalyDetail:
    anomaly = _get_anomaly_or_404(db, anomaly_id)
    return AnomalyDetail.model_validate(anomaly)


@router.patch("/{anomaly_id}/status", response_model=AnomalyDetail)
def change_anomaly_status(
    anomaly_id: UUID,
    payload: AnomalyStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(write_required),
) -> AnomalyDetail:
    anomaly = _get_anomaly_or_404(db, anomaly_id)
    try:
        updated = update_anomaly_status(db, anomaly, payload, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    record_audit_event(
        db,
        user,
        "anomaly.status_change",
        "anomaly",
        str(updated.id),
        severity="critical" if payload.status.value == "incident" else "info",
        details={"status": payload.status.value, "comment": payload.comment},
    )
    return AnomalyDetail.model_validate(updated)


def _get_anomaly_or_404(db: Session, anomaly_id: UUID):
    anomaly = get_anomaly(db, anomaly_id)
    if anomaly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomaly not found",
        )
    return anomaly
