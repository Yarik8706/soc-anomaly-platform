from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.schemas.analysis_run import AnalysisRunCreate
from app.services.pipeline import initial_stages
from app.services.task_queue import enqueue_run


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
        upload_ids=[str(value) for value in payload.upload_ids],
        stages=initial_stages(),
        artifacts={},
    )

    db.add(analysis_run)
    db.commit()
    db.refresh(analysis_run)

    return analysis_run


def queue_analysis_run(db: Session, analysis_run: AnalysisRun) -> AnalysisRun:
    analysis_run.status = "queued"
    analysis_run.attempts += 1
    analysis_run.error_message = None
    analysis_run.finished_at = None
    db.commit()
    try:
        analysis_run.job_id = enqueue_run(str(analysis_run.id))
    except Exception as exc:
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.finished_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        raise
    db.commit()
    db.refresh(analysis_run)
    return analysis_run


def retry_analysis_run(db: Session, analysis_run: AnalysisRun) -> AnalysisRun:
    if analysis_run.status not in {"failed", "completed"}:
        raise ValueError("Only failed or completed runs can be queued again")
    analysis_run.stages = initial_stages()
    analysis_run.current_stage = None
    return queue_analysis_run(db, analysis_run)


def list_analysis_runs(db: Session) -> list[AnalysisRun]:
    statement = select(AnalysisRun).order_by(AnalysisRun.created_at.desc())
    return list(db.scalars(statement).all())


def get_analysis_run(db: Session, run_id: str) -> AnalysisRun | None:
    return db.get(AnalysisRun, run_id)
