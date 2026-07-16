from app.core.db import SessionLocal
from app.models.analysis_run import AnalysisRun
from app.services.pipeline import execute_analysis_run


def process_analysis_run(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.get(AnalysisRun, run_id)
        if run is None:
            raise LookupError(f"Analysis run {run_id} was not found")
        execute_analysis_run(db, run)
