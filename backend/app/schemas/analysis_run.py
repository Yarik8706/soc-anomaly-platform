from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalysisScope(StrEnum):
    day = "day"
    week = "week"
    month = "month"
    range = "range"
    all = "all"


class AnalysisMode(StrEnum):
    report = "report"
    metrics = "metrics"
    report_metrics = "report+metrics"
    full = "full"
    dry_run = "dry-run"


class AnalysisParameters(BaseModel):
    """Validated model and reporting settings persisted with every run."""

    mode: AnalysisMode = AnalysisMode.full
    contamination: float = Field(default=0.05, gt=0, le=0.5)
    n_estimators: int = Field(default=300, ge=10, le=5_000)
    n_neighbors: int = Field(default=20, ge=1, le=10_000)
    random_state: int = 42
    max_samples: str | int | float = "auto"
    top_features: int = Field(default=5, ge=1, le=100)
    top_pct: float = Field(default=0.05, gt=0, le=1)
    top_n: int = Field(default=30, ge=1, le=10_000)
    k_values: list[int] = Field(default_factory=lambda: [5, 10, 20])
    contamination_grid: list[float] | None = None
    n_neighbors_grid: list[int] | None = None
    stability_all_dates: bool = False
    run_tag: str | None = Field(default=None, max_length=120)

    @field_validator("max_samples")
    @classmethod
    def validate_max_samples(cls, value: str | int | float) -> str | int | float:
        if isinstance(value, str):
            if value.casefold() != "auto":
                raise ValueError("max_samples must be 'auto', a positive integer or a float in (0, 1]")
            return "auto"
        if isinstance(value, int):
            if value < 1:
                raise ValueError("integer max_samples must be positive")
            return value
        if not 0 < value <= 1:
            raise ValueError("float max_samples must be in (0, 1]")
        return value

    @field_validator("k_values")
    @classmethod
    def validate_k_values(cls, values: list[int]) -> list[int]:
        normalized = sorted({int(value) for value in values})
        if not normalized or normalized[0] <= 0:
            raise ValueError("k_values must contain positive integers")
        return normalized

    @field_validator("contamination_grid")
    @classmethod
    def validate_contamination_grid(cls, values: list[float] | None) -> list[float] | None:
        if values is None:
            return values
        if not values or any(not 0 < value <= 0.5 for value in values):
            raise ValueError("contamination_grid values must be in (0, 0.5]")
        return sorted(set(values))

    @field_validator("n_neighbors_grid")
    @classmethod
    def validate_neighbors_grid(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return values
        if not values or any(value <= 0 for value in values):
            raise ValueError("n_neighbors_grid values must be positive")
        return sorted(set(values))


class AnalysisRunCreate(BaseModel):
    scope: AnalysisScope = Field(examples=["day"])
    target_date: date | None = Field(default=None, examples=["2025-12-31"])
    start_date: date | None = None
    end_date: date | None = None
    parameters: AnalysisParameters | None = Field(default_factory=AnalysisParameters)
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
