from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProxyMetricsRead(BaseModel):
    run_id: UUID
    generated_at: datetime
    score_distributions: dict[str, Any]
    distribution_statistics: dict[str, Any] = Field(default_factory=dict)
    stability: dict[str, Any]
    stability_experiments: dict[str, Any] = Field(default_factory=dict)
    explainability: dict[str, Any] = Field(default_factory=dict)
    contributing_features: dict[str, int]
    k_values: list[int] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
