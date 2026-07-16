from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.analysis_run import AnalysisRunCreate, AnalysisRunRead
from app.services.analysis_run import (
    create_analysis_run,
    get_analysis_run,
    list_analysis_runs,
    queue_analysis_run,
    retry_analysis_run,
)
from app.services.task_queue import TaskQueueError

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post(
    "",
    response_model=AnalysisRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    payload: AnalysisRunCreate,
    db: Session = Depends(get_db),
):
    analysis_run = create_analysis_run(db, payload)
    try:
        return queue_analysis_run(db, analysis_run)
    except TaskQueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[AnalysisRunRead])
def get_runs(db: Session = Depends(get_db)):
    return list_analysis_runs(db)


@router.get("/{run_id}", response_model=AnalysisRunRead)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    analysis_run = get_analysis_run(db, str(run_id))

    if analysis_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis run not found",
        )

    return analysis_run


@router.post("/{run_id}/retry", response_model=AnalysisRunRead)
def retry_run(run_id: UUID, db: Session = Depends(get_db)):
    analysis_run = get_analysis_run(db, str(run_id))
    if analysis_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis run not found",
        )
    try:
        return retry_analysis_run(db, analysis_run)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except TaskQueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
