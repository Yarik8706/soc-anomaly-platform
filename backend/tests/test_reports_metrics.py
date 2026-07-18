from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.db.base import Base
from app.main import app
from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly, AnomalyExplanation
from app.models.user import User
from app.services.auth import get_current_user
from app.services.metrics import get_proxy_metrics
from app.services.reports import create_report, generate_report


def _engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _run(db: Session, created_at: datetime | None = None) -> AnalysisRun:
    run = AnalysisRun(
        status="completed",
        scope="day",
        target_date="2026-07-15",
        created_at=created_at or datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(run)
    db.flush()
    return run


def _anomaly(
    db: Session, run: AnalysisRun, entity: str, rank: int, score: float
) -> Anomaly:
    anomaly = Anomaly(
        run_id=run.id,
        entity_type="user",
        entity=entity,
        date=date(2026, 7, 15),
        severity="critical" if rank == 1 else "high",
        score=score,
        rank=rank,
        summary="Unusual night activity",
        context={"active_hours": ["2"]},
    )
    anomaly.explanations = [
        AnomalyExplanation(
            feature_name="night_share",
            feature_value=1.0,
            baseline_value=0.0,
            contribution=4.0,
        )
    ]
    db.add(anomaly)
    return anomaly


def test_report_generation_creates_markdown_pdf_and_download_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    from app.services import reports

    monkeypatch.setattr(reports.settings, "analysis_directory", tmp_path / "runs")
    monkeypatch.setattr(reports, "enqueue_report", lambda report_id: f"job-{report_id}")
    with Session(engine) as db:
        run = _run(db)
        _anomaly(db, run, "user001", 1, 0.99)
        db.commit()
        queued = create_report(db, run)
        assert queued.status == "queued"
        assert queued.job_id == f"job-{queued.id}"
        completed = generate_report(db, queued)
        assert completed.status == "completed"
        assert Path(completed.markdown_path).read_text(encoding="utf-8").startswith(
            "# SOC Anomaly Report"
        )
        assert Path(completed.pdf_path).read_bytes().startswith(b"%PDF")
        report_id = completed.id

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid4(),
        email="analyst@example.test",
        password_hash="unused",
        role="analyst",
        is_active=True,
    )
    try:
        with TestClient(app) as client:
            detail = client.get(f"/reports/{report_id}")
            content = client.get(f"/reports/{report_id}/content")
            pdf = client.get(f"/reports/{report_id}/download/pdf")
            context = client.get(f"/reports/{report_id}/download/context")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert {item["format"] for item in detail.json()["files"]} == {
        "markdown",
        "pdf",
        "context",
    }
    assert "Severity summary" in content.text
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert context.status_code == 200
    assert context.headers["content-type"].startswith("text/csv")


def test_proxy_metrics_include_distributions_stability_and_features() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as db:
        previous = _run(db, now - timedelta(days=1))
        _anomaly(db, previous, "user001", 1, 0.9)
        _anomaly(db, previous, "user002", 2, 0.7)
        current = _run(db, now)
        _anomaly(db, current, "user001", 1, 0.95)
        _anomaly(db, current, "user003", 2, 0.6)
        db.commit()

        metric = get_proxy_metrics(db, current)

        assert sum(metric.result["score_distributions"]["user"]["counts"]) == 2
        assert metric.result["stability"]["user"]["jaccard_at_k"] == pytest.approx(1 / 3)
        assert metric.result["stability"]["user"]["overlap_at_k"] == pytest.approx(0.5)
        assert metric.result["contributing_features"]["night_share"] == 2
