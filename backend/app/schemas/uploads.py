from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class UploadedFileRead(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size: int
    status: str
    uploaded_by: UUID | None
    created_at: datetime
    validation_result: dict[str, Any] | None
    validated_at: datetime | None
    normalization_result: dict[str, Any] | None
    normalized_at: datetime | None

    model_config = {"from_attributes": True}
