from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AnomalyStatus(StrEnum):
    new = "new"
    investigating = "investigating"
    incident = "incident"
    false_positive = "false_positive"
    closed = "closed"


class AnomalyExplanationRead(BaseModel):
    feature_name: str
    feature_value: float
    baseline_value: float
    contribution: float

    model_config = {"from_attributes": True}


class AnomalyActivityRead(BaseModel):
    id: UUID
    actor_id: UUID | None
    previous_status: str
    new_status: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnomalyRead(BaseModel):
    id: UUID
    run_id: UUID
    entity_type: str
    entity: str
    date: date
    severity: str
    score: float
    rank: int
    score_isolation_forest: float | None = None
    score_isolation_forest_norm: float | None = None
    rank_isolation_forest: int | None = None
    score_lof: float | None = None
    score_lof_norm: float | None = None
    rank_lof: int | None = None
    score_combined: float | None = None
    rank_combined: int | None = None
    summary: str
    status: str
    context: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnomalyDetail(AnomalyRead):
    explanations: list[AnomalyExplanationRead]
    activities: list[AnomalyActivityRead]


class AnomalyList(BaseModel):
    items: list[AnomalyRead]
    total: int
    offset: int
    limit: int
    counters: dict[str, int]


class AnomalyStatusUpdate(BaseModel):
    status: AnomalyStatus
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_resolution_comment(self):
        if self.status in {
            AnomalyStatus.incident,
            AnomalyStatus.false_positive,
            AnomalyStatus.closed,
        } and not (self.comment and self.comment.strip()):
            raise ValueError("A comment is required for incident, false_positive or closed")
        return self
