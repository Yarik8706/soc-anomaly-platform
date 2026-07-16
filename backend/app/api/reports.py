from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.analysis_run import AnalysisRun
from app.models.report import Report
from app.models.user import User
from app.schemas.auth import UserRole
from app.schemas.reports import ReportRead
from app.services.audit import record_audit_event
from app.services.auth import require_roles
from app.services.reports import (
    create_report,
    get_report,
    list_reports,
    report_path,
    report_read,
)
from app.services.task_queue import TaskQueueError

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_roles(*UserRole))],
)
write_required = require_roles(UserRole.admin, UserRole.analyst)


@router.post("/runs/{run_id}", response_model=ReportRead, status_code=status.HTTP_202_ACCEPTED)
def request_report(
    run_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(write_required),
) -> ReportRead:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
        )
    try:
        report = create_report(db, run)
        record_audit_event(
            db,
            user,
            "report.create",
            "report",
            str(report.id),
            details={"run_id": str(run.id)},
        )
        return report_read(report)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskQueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.get("", response_model=list[ReportRead])
def get_reports(
    run_id: UUID | None = None, db: Session = Depends(get_db)
) -> list[ReportRead]:
    return [report_read(report) for report in list_reports(db, run_id)]


@router.get("/{report_id}", response_model=ReportRead)
def get_report_detail(report_id: UUID, db: Session = Depends(get_db)) -> ReportRead:
    return report_read(_get_report_or_404(db, report_id))


@router.get("/{report_id}/content", response_class=PlainTextResponse)
def get_report_content(report_id: UUID, db: Session = Depends(get_db)) -> str:
    report = _get_report_or_404(db, report_id)
    try:
        return report_path(report, "markdown").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{report_id}/download/{format_name}", response_class=FileResponse)
def download_report(
    report_id: UUID,
    format_name: Literal["markdown", "pdf"],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*UserRole)),
):
    report = _get_report_or_404(db, report_id)
    try:
        path = report_path(report, format_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    media_type = "text/markdown; charset=utf-8" if format_name == "markdown" else "application/pdf"
    record_audit_event(
        db,
        user,
        "report.export",
        "report",
        str(report.id),
        details={"format": format_name},
    )
    return FileResponse(path, media_type=media_type, filename=path.name)


def _get_report_or_404(db: Session, report_id: UUID) -> Report:
    report = get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report
