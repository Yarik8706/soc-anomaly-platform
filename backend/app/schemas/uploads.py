from datetime import datetime
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

    model_config = {"from_attributes": True}
