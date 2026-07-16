from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly
from app.models.uploaded_file import UploadedFile
from app.schemas.analysis_run import AnalysisRunCreate
from app.services.analysis_run import create_analysis_run, queue_analysis_run, retry_analysis_run
from app.services.features import build_features
from app.services.pipeline import execute_analysis_run
from app.services.scoring import ScoreConfig, score_feature_file


def _normalized_log(path: Path) -> None:
    rows = [
        ("2026-07-14 10:00:00", "user001", "user002", "host-a", "Login", "proc-a", "10.0.0.1"),
        ("2026-07-14 11:00:00", "user002", "user001", "host-b", "Login", "proc-a", "10.0.0.2"),
        ("2026-07-15 02:00:00", "user001", "user003", "host-a", "Admin", "powershell", "8.8.8.8"),
        ("2026-07-15 02:01:00", "user001", "user003", "host-a", "Admin", "powershell", "8.8.4.4"),
        ("2026-07-15 12:00:00", "user002", "user001", "host-b", "Login", "proc-a", "10.0.0.2"),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "Timestamp",
            "SourceUserName",
            "DestinationUserName",
            "Host",
            "Name",
            "SourceProcessName",
            "DestinationAddress",
        ],
    )
    frame["Date"] = pd.to_datetime(frame["Timestamp"]).dt.strftime("%Y-%m-%d")
    frame.to_csv(path, index=False)


def test_feature_builder_and_scoring_support_users_and_hosts(tmp_path: Path) -> None:
    input_path = tmp_path / "normalized.csv"
    _normalized_log(input_path)

    outputs = build_features([input_path], tmp_path / "features")

    assert set(outputs) == {"users", "hosts"}
    users = pd.read_csv(outputs["users"])
    hosts = pd.read_csv(outputs["hosts"])
    assert {"user001", "user002", "user003"} == set(users["entity"])
    assert {"host-a", "host-b"} == set(hosts["entity"])

    scores = score_feature_file(
        outputs["users"], "2026-07-15", ScoreConfig(top_n=10, n_estimators=10)
    )
    assert {"score_isolation_forest", "score_lof", "score", "rank"}.issubset(scores)
    assert scores["rank"].tolist() == list(range(1, len(scores) + 1))


def test_pipeline_persists_stage_history_artifacts_and_explanations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "normalized.csv"
    _normalized_log(input_path)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    from app.services import pipeline

    monkeypatch.setattr(pipeline.settings, "analysis_directory", tmp_path / "runs")
    with Session(engine) as db:
        upload = UploadedFile(
            filename="events.csv",
            content_type="text/csv",
            size=input_path.stat().st_size,
            storage_path=str(input_path),
            status="normalized",
            normalization_result={"artifacts": [{"path": str(input_path)}]},
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)
        run = AnalysisRun(
            status="queued",
            scope="day",
            target_date="2026-07-15",
            upload_ids=[str(upload.id)],
            parameters={"n_estimators": 10, "top_n": 10},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        result = execute_analysis_run(db, run)

        assert result.status == "completed"
        assert result.current_stage is None
        assert result.stages["features"]["status"] == "completed"
        assert result.stages["scoring"]["status"] == "completed"
        assert result.stages["explain"]["status"] == "completed"
        assert Path(result.artifacts["features"]["users"]).is_file()
        anomalies = list(db.scalars(select(Anomaly).where(Anomaly.run_id == run.id)))
        assert anomalies
        assert all(anomaly.explanations for anomaly in anomalies)
        assert {anomaly.entity_type for anomaly in anomalies} == {"user", "host"}


def test_failed_or_completed_run_can_be_queued_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from app.services import analysis_run

    monkeypatch.setattr(analysis_run, "enqueue_run", lambda run_id: f"job-{run_id}")
    with Session(engine) as db:
        payload = AnalysisRunCreate(
            scope="day",
            target_date="2026-07-15",
            upload_ids=["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
        )
        run = create_analysis_run(db, payload)
        queued = queue_analysis_run(db, run)
        assert queued.status == "queued"
        assert queued.attempts == 1
        assert queued.job_id == f"job-{queued.id}"

        queued.status = "failed"
        db.commit()
        retried = retry_analysis_run(db, queued)
        assert retried.status == "queued"
        assert retried.attempts == 2
