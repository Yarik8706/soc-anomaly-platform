from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.user import User


def record_audit_event(
    db: Session,
    user: User | None,
    action: str,
    object_type: str,
    object_id: str | None,
    *,
    severity: str = "info",
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user.id if user else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        severity=severity,
        details=details,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_audit_events(
    db: Session,
    *,
    action: str | None = None,
    severity: str | None = None,
    object_type: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[AuditEvent], int]:
    filters = []
    if action:
        filters.append(AuditEvent.action == action)
    if severity:
        filters.append(AuditEvent.severity == severity)
    if object_type:
        filters.append(AuditEvent.object_type == object_type)
    items = list(
        db.scalars(
            select(AuditEvent)
            .where(*filters)
            .order_by(AuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    return items, int(total)
