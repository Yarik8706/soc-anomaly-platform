from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.analysis_run import AnalysisRunCreate, AnalysisRunRead
from app.services.analysis_run import (
    create_analysis_run,
    get_analysis_run,
    list_analysis_runs,
)

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
    return create_analysis_run(db, payload)


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
