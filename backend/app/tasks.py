from app.core.db import SessionLocal
from app.models.analysis_run import AnalysisRun
from app.models.report import Report
from app.services.pipeline import execute_analysis_run
from app.services.reports import generate_report


def process_analysis_run(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.get(AnalysisRun, run_id)
        if run is None:
            raise LookupError(f"Analysis run {run_id} was not found")
        execute_analysis_run(db, run)


def process_report(report_id: str) -> None:
    with SessionLocal() as db:
        report = db.get(Report, report_id)
        if report is None:
            raise LookupError(f"Report {report_id} was not found")
        generate_report(db, report)
