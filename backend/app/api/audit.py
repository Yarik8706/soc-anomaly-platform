from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.user import User
from app.schemas.audit import AuditEventList, AuditEventRead
from app.schemas.auth import UserRole
from app.services.audit import list_audit_events
from app.services.auth import require_roles

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditEventList)
def get_audit_log(
    action: str | None = None,
    severity: str | None = None,
    object_type: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.admin)),
) -> AuditEventList:
    items, total = list_audit_events(
        db,
        action=action,
        severity=severity,
        object_type=object_type,
        offset=offset,
        limit=limit,
    )
    return AuditEventList(
        items=[AuditEventRead.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )
