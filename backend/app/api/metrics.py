from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.analysis_run import AnalysisRun
from app.schemas.metrics import ProxyMetricsRead
from app.schemas.auth import UserRole
from app.services.auth import require_roles
from app.services.metrics import get_proxy_metrics

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_roles(*UserRole))],
)


@router.get("/runs/{run_id}", response_model=ProxyMetricsRead)
def get_run_metrics(run_id: UUID, db: Session = Depends(get_db)) -> ProxyMetricsRead:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
        )
    metric = get_proxy_metrics(db, run)
    return ProxyMetricsRead.model_validate(metric.result)
