from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AnalysisScope(StrEnum):
    day = "day"
    week = "week"
    month = "month"
    range = "range"
    all = "all"


class AnalysisRunCreate(BaseModel):
    scope: AnalysisScope = Field(examples=["day"])
    target_date: date | None = Field(default=None, examples=["2025-12-31"])
    start_date: date | None = None
    end_date: date | None = None
    parameters: dict[str, Any] | None = None
    upload_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.scope
            in {
                AnalysisScope.day,
                AnalysisScope.week,
                AnalysisScope.month,
            }
            and self.target_date is None
        ):
            raise ValueError("target_date is required for day, week and month scopes")

        if self.scope == AnalysisScope.range:
            if self.start_date is None or self.end_date is None:
                raise ValueError("start_date and end_date are required for range scope")

            if self.start_date > self.end_date:
                raise ValueError("start_date must be before or equal to end_date")

        return self


class AnalysisRunRead(BaseModel):
    id: UUID
    status: str
    scope: str
    target_date: str | None
    start_date: str | None
    end_date: str | None
    parameters: dict[str, Any] | None
    upload_ids: list[str] | None
    stages: dict[str, Any] | None
    artifacts: dict[str, Any] | None
    current_stage: str | None
    job_id: str | None
    attempts: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {
        "from_attributes": True,
    }
