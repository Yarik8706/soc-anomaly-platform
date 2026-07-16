from datetime import date
from uuid import uuid4

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


def _analyst() -> User:
    return User(
        id=uuid4(),
        email="analyst@example.test",
        password_hash="unused",
        role="analyst",
        is_active=True,
    )


def _test_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_anomaly_dashboard_filters_counters_and_detail() -> None:
    engine = _test_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        run = AnalysisRun(status="completed", scope="day", target_date="2026-07-15")
        db.add(run)
        db.flush()
        first = Anomaly(
            run_id=run.id,
            entity_type="user",
            entity="user001",
            date=date(2026, 7, 15),
            severity="critical",
            score=0.99,
            rank=1,
            summary="Unusual night activity",
            context={"ip_addresses": ["8.8.8.8"], "active_hours": ["2"]},
        )
        first.explanations = [
            AnomalyExplanation(
                feature_name="night_share",
                feature_value=1.0,
                baseline_value=0.0,
                contribution=4.2,
            )
        ]
        db.add_all(
            [
                first,
                Anomaly(
                    run_id=run.id,
                    entity_type="host",
                    entity="host-a",
                    date=date(2026, 7, 15),
                    severity="medium",
                    score=0.4,
                    rank=2,
                    summary="Unusual process count",
                ),
            ]
        )
        db.commit()
        db.refresh(first)
        anomaly_id = first.id

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _analyst
    try:
        with TestClient(app) as client:
            response = client.get("/anomalies", params={"entity_type": "user"})
            detail = client.get(f"/anomalies/{anomaly_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["counters"] == {"critical": 1, "total": 1}
    assert response.json()["items"][0]["entity"] == "user001"
    assert detail.status_code == 200
    assert detail.json()["explanations"][0]["feature_name"] == "night_share"
    assert detail.json()["context"]["ip_addresses"] == ["8.8.8.8"]


def test_anomaly_workflow_requires_resolution_comment_and_keeps_history() -> None:
    engine = _test_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        run = AnalysisRun(status="completed", scope="day", target_date="2026-07-15")
        db.add(run)
        db.flush()
        anomaly = Anomaly(
            run_id=run.id,
            entity_type="user",
            entity="user001",
            date=date(2026, 7, 15),
            severity="high",
            score=0.8,
            rank=1,
            summary="Unusual activity",
        )
        db.add(anomaly)
        db.commit()
        db.refresh(anomaly)
        anomaly_id = anomaly.id

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _analyst
    try:
        with TestClient(app) as client:
            invalid = client.patch(
                f"/anomalies/{anomaly_id}/status", json={"status": "incident"}
            )
            investigating = client.patch(
                f"/anomalies/{anomaly_id}/status",
                json={"status": "investigating", "comment": "Checking source host"},
            )
            incident = client.patch(
                f"/anomalies/{anomaly_id}/status",
                json={"status": "incident", "comment": "Confirmed compromise"},
            )
    finally:
        app.dependency_overrides.clear()

    assert invalid.status_code == 422
    assert investigating.status_code == 200
    assert incident.status_code == 200
    payload = incident.json()
    assert payload["status"] == "incident"
    assert [activity["new_status"] for activity in payload["activities"]] == [
        "investigating",
        "incident",
    ]
