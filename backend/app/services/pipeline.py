from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly, AnomalyExplanation
from app.models.uploaded_file import UploadedFile
from app.services.explanations import explain_row, severity_for_rank
from app.services.features import build_features
from app.services.scoring import ScoreConfig, score_feature_file

STAGES = ("import", "features", "scoring", "explain", "reports")


class PipelineError(RuntimeError):
    pass


def initial_stages() -> dict[str, dict[str, str | None]]:
    return {
        stage: {
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
        for stage in STAGES
    }


def execute_analysis_run(db: Session, run: AnalysisRun) -> AnalysisRun:
    run.status = "running"
    run.started_at = run.started_at or _now()
    run.finished_at = None
    run.error_message = None
    run.artifacts = {}
    db.commit()

    try:
        input_paths = _stage(db, run, "import", lambda: _input_paths(db, run))
        feature_paths = _stage(
            db,
            run,
            "features",
            lambda: build_features(
                input_paths,
                settings.analysis_directory / str(run.id) / "features",
            ),
        )
        _merge_artifacts(run, "features", feature_paths)
        db.commit()

        scored = _stage(db, run, "scoring", lambda: _score(feature_paths, run))
        _stage(db, run, "explain", lambda: _persist_anomalies(db, run, feature_paths, scored))
        _skip_stage(run, "reports")
        run.status = "completed"
        run.current_stage = None
        run.finished_at = _now()
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = _now()
        db.commit()
        raise


def _stage(db: Session, run: AnalysisRun, name: str, operation):
    stages = dict(run.stages or initial_stages())
    stages[name] = {
        "status": "running",
        "started_at": _now().isoformat(),
        "finished_at": None,
        "error": None,
    }
    run.stages = stages
    run.current_stage = name
    db.commit()
    try:
        result = operation()
    except Exception as exc:
        stages = dict(run.stages or {})
        stages[name] = {
            **stages[name],
            "status": "failed",
            "finished_at": _now().isoformat(),
            "error": str(exc),
        }
        run.stages = stages
        db.commit()
        raise
    stages = dict(run.stages or {})
    stages[name] = {
        **stages[name],
        "status": "completed",
        "finished_at": _now().isoformat(),
    }
    run.stages = stages
    db.commit()
    return result


def _skip_stage(run: AnalysisRun, name: str) -> None:
    stages = dict(run.stages or {})
    stages[name] = {**stages[name], "status": "pending"}
    run.stages = stages


def _input_paths(db: Session, run: AnalysisRun) -> list[Path]:
    ids = [UUID(value) for value in run.upload_ids or []]
    uploads = list(db.scalars(select(UploadedFile).where(UploadedFile.id.in_(ids))))
    if len(uploads) != len(ids):
        raise PipelineError("One or more selected uploads do not exist")

    paths: list[Path] = []
    for upload in uploads:
        if upload.status != "normalized" or not upload.normalization_result:
            raise PipelineError(f"Upload {upload.id} is not normalized")
        for artifact in upload.normalization_result.get("artifacts", []):
            path = Path(artifact.get("path", ""))
            if path.is_file():
                paths.append(path)
    if not paths:
        raise PipelineError("Selected uploads have no normalized artifacts")
    return paths


def _score(feature_paths: dict[str, Path], run: AnalysisRun) -> dict[str, pd.DataFrame]:
    parameters = run.parameters or {}
    config = ScoreConfig(
        contamination=float(parameters.get("contamination", 0.05)),
        n_estimators=int(parameters.get("n_estimators", 300)),
        n_neighbors=int(parameters.get("n_neighbors", 20)),
        top_n=int(parameters.get("top_n", 30)),
        random_state=int(parameters.get("random_state", 42)),
    )
    target_date = _target_date(run)
    return {
        kind: score_feature_file(path, target_date, config)
        for kind, path in feature_paths.items()
    }


def _persist_anomalies(
    db: Session,
    run: AnalysisRun,
    feature_paths: dict[str, Path],
    scored: dict[str, pd.DataFrame],
) -> int:
    db.execute(delete(Anomaly).where(Anomaly.run_id == run.id))
    count = 0
    anomaly_directory = settings.analysis_directory / str(run.id) / "anomalies"
    anomaly_directory.mkdir(parents=True, exist_ok=True)

    for kind, scored_frame in scored.items():
        features = pd.read_csv(feature_paths[kind])
        output = anomaly_directory / f"anomalies_{kind}.csv"
        scored_frame.to_csv(output, index=False)
        _merge_artifacts(run, f"anomalies_{kind}", output)
        total = len(scored_frame)
        for _, row in scored_frame.iterrows():
            explanations = explain_row(features, row, str(row["date"]))
            severity = severity_for_rank(int(row["rank"]), total)
            leading = explanations[0]["feature_name"] if explanations else "combined score"
            anomaly = Anomaly(
                run_id=run.id,
                entity_type="user" if kind == "users" else "host",
                entity=str(row["entity"]),
                date=row["date"],
                severity=severity,
                score=float(row["score"]),
                rank=int(row["rank"]),
                summary=f"Unusual {leading} compared with historical baseline",
                context={"isolation_forest": float(row["score_isolation_forest"]), "lof": float(row["score_lof"])},
            )
            anomaly.explanations = [AnomalyExplanation(**item) for item in explanations]
            db.add(anomaly)
            count += 1
    db.commit()
    return count


def _target_date(run: AnalysisRun) -> str | None:
    if run.scope in {"day", "week", "month"}:
        return run.target_date
    if run.scope == "range":
        return run.end_date
    return None


def _merge_artifacts(run: AnalysisRun, key: str, value) -> None:
    artifacts = dict(run.artifacts or {})
    if isinstance(value, dict):
        artifacts[key] = {name: str(path) for name, path in value.items()}
    else:
        artifacts[key] = str(value)
    run.artifacts = artifacts


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
