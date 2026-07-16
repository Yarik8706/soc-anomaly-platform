from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ProxyMetricsRead(BaseModel):
    run_id: UUID
    generated_at: datetime
    score_distributions: dict[str, Any]
    stability: dict[str, Any]
    contributing_features: dict[str, int]
