from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEventRead(BaseModel):
    id: UUID
    user_id: UUID | None
    action: str
    object_type: str
    object_id: str | None
    severity: str
    details: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditEventList(BaseModel):
    items: list[AuditEventRead]
    total: int
    offset: int
    limit: int
