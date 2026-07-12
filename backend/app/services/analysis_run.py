from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.schemas.analysis_run import AnalysisRunCreate


def _date_to_str(value):
    return value.isoformat() if value is not None else None


def create_analysis_run(db: Session, payload: AnalysisRunCreate) -> AnalysisRun:
    analysis_run = AnalysisRun(
        status="pending",
        scope=payload.scope.value,
        target_date=_date_to_str(payload.target_date),
        start_date=_date_to_str(payload.start_date),
        end_date=_date_to_str(payload.end_date),
        parameters=payload.parameters,
    )

    db.add(analysis_run)
    db.commit()
    db.refresh(analysis_run)

    return analysis_run


def list_analysis_runs(db: Session) -> list[AnalysisRun]:
    statement = select(AnalysisRun).order_by(AnalysisRun.created_at.desc())
    return list(db.scalars(statement).all())


def get_analysis_run(db: Session, run_id: str) -> AnalysisRun | None:
    return db.get(AnalysisRun, run_id)
