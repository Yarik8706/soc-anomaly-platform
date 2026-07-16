from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from uuid import UUID

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly
from app.models.report import Report
from app.schemas.reports import ReportFileRead, ReportRead
from app.services.task_queue import enqueue_report


def create_report(db: Session, run: AnalysisRun) -> Report:
    if run.status != "completed":
        raise ValueError("A report can only be generated for a completed run")
    active = db.scalar(
        select(Report).where(
            Report.run_id == run.id,
            Report.status.in_(("queued", "running")),
        )
    )
    if active:
        raise ValueError("A report is already being generated for this run")

    report = Report(run_id=run.id, status="queued")
    db.add(report)
    db.commit()
    db.refresh(report)
    try:
        report.job_id = enqueue_report(str(report.id))
    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)
        report.finished_at = _now()
        db.commit()
        raise
    db.commit()
    db.refresh(report)
    return report


def generate_report(db: Session, report: Report) -> Report:
    report.status = "running"
    report.error_message = None
    db.commit()
    try:
        run = db.get(AnalysisRun, report.run_id)
        if run is None:
            raise LookupError("Analysis run not found")
        anomalies = list(
            db.scalars(
                select(Anomaly)
                .where(Anomaly.run_id == report.run_id)
                .options(selectinload(Anomaly.explanations))
                .order_by(Anomaly.rank)
            ).all()
        )
        output = settings.analysis_directory / str(report.run_id) / "reports" / str(report.id)
        output.mkdir(parents=True, exist_ok=True)
        markdown_path = output / "soc_report.md"
        pdf_path = output / "soc_report.pdf"
        markdown = _markdown(run, anomalies)
        markdown_path.write_text(markdown, encoding="utf-8")
        _pdf(pdf_path, run, anomalies)
        report.markdown_path = str(markdown_path)
        report.pdf_path = str(pdf_path)
        report.status = "completed"
        report.finished_at = _now()
        db.commit()
        db.refresh(report)
        return report
    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)
        report.finished_at = _now()
        db.commit()
        raise


def list_reports(db: Session, run_id: UUID | None = None) -> list[Report]:
    statement = select(Report).order_by(Report.created_at.desc())
    if run_id:
        statement = statement.where(Report.run_id == run_id)
    return list(db.scalars(statement).all())


def get_report(db: Session, report_id: UUID) -> Report | None:
    return db.get(Report, report_id)


def report_read(report: Report) -> ReportRead:
    files = []
    for format_name, value in (("markdown", report.markdown_path), ("pdf", report.pdf_path)):
        if value and (path := Path(value)).is_file():
            files.append(
                ReportFileRead(
                    format=format_name,
                    filename=path.name,
                    size=path.stat().st_size,
                    url=f"/reports/{report.id}/download/{format_name}",
                )
            )
    return ReportRead(
        id=report.id,
        run_id=report.run_id,
        status=report.status,
        job_id=report.job_id,
        error_message=report.error_message,
        created_at=report.created_at,
        finished_at=report.finished_at,
        files=files,
    )


def report_path(report: Report, format_name: str) -> Path:
    value = report.markdown_path if format_name == "markdown" else report.pdf_path
    if not value:
        raise FileNotFoundError(f"{format_name} report is not available")
    path = Path(value).resolve()
    report_root = (settings.analysis_directory / str(report.run_id) / "reports").resolve()
    if not path.is_relative_to(report_root) or not path.is_file():
        raise FileNotFoundError(f"{format_name} report is not available")
    return path


def _markdown(run: AnalysisRun, anomalies: list[Anomaly]) -> str:
    counts = Counter(anomaly.severity for anomaly in anomalies)
    lines = [
        "# SOC Anomaly Report",
        "",
        f"Analysis run: `{run.id}`",
        f"Scope: **{run.scope}**",
        f"Generated: {_now().isoformat()}Z",
        "",
        "## Severity summary",
        "",
    ]
    for severity in ("critical", "high", "medium", "low"):
        lines.append(f"- {severity}: {counts.get(severity, 0)}")
    lines.extend(
        [
            "",
            "## Anomalies",
            "",
            "| Rank | Type | Entity | Date | Severity | Score | Summary |",
            "| ---: | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for anomaly in anomalies:
        summary = anomaly.summary.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {anomaly.rank} | {anomaly.entity_type} | {anomaly.entity} | "
            f"{anomaly.date} | {anomaly.severity} | {anomaly.score:.4f} | {summary} |"
        )
    return "\n".join(lines) + "\n"


def _pdf(path: Path, run: AnalysisRun, anomalies: list[Anomaly]) -> None:
    styles = getSampleStyleSheet()
    story = [
        Paragraph("SOC Anomaly Report", styles["Title"]),
        Paragraph(f"Analysis run: {escape(str(run.id))}", styles["BodyText"]),
        Spacer(1, 12),
    ]
    counts = Counter(anomaly.severity for anomaly in anomalies)
    story.append(
        Table(
            [["Severity", "Count"]]
            + [[name, str(counts.get(name, 0))] for name in ("critical", "high", "medium", "low")]
        )
    )
    story.append(Spacer(1, 12))
    rows = [["Rank", "Type", "Entity", "Severity", "Score"]]
    rows.extend(
        [
            str(anomaly.rank),
            anomaly.entity_type,
            anomaly.entity[:32],
            anomaly.severity,
            f"{anomaly.score:.4f}",
        ]
        for anomaly in anomalies[:100]
    )
    story.append(Table(rows, repeatRows=1))
    SimpleDocTemplate(str(path), pagesize=A4, title="SOC Anomaly Report").build(story)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
