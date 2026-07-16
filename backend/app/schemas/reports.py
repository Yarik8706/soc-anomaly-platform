from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReportFileRead(BaseModel):
    format: str
    filename: str
    size: int
    url: str


class ReportRead(BaseModel):
    id: UUID
    run_id: UUID
    status: str
    job_id: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    files: list[ReportFileRead]


class ReportContent(BaseModel):
    id: UUID
    content: str
