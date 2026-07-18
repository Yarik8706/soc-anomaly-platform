from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly, AnomalyExplanation
from app.models.uploaded_file import UploadedFile
from app.services.anomaly_context import AnomalyContextBuilder
from app.services.anonymization import (
    AnalysisInputBundle,
    load_reverse_mapping,
    prepare_analysis_inputs,
)
from app.services.explanations import explain_row, severity_for_rank
from app.services.features import available_feature_dates, build_features
from app.services.metrics import generate_proxy_metrics
from app.services.reports import generate_automatic_report
from app.services.reproducibility import (
    finalize_manifest,
    initialize_run_metadata,
    write_run_config,
)
from app.services.scoring import ScoreConfig, score_feature_file
from app.services.visualizations import generate_graphical_reports

STAGES = ("import", "features", "scoring", "explain", "metrics", "reports")
REPORT_MODES = {"report", "report+metrics", "full"}
METRICS_MODES = {"metrics", "report+metrics", "full"}


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
    run_root = settings.analysis_directory / str(run.id)
    config = _score_config(run)
    manifest_path: Path | None = None
    run.status = "running"
    run.started_at = run.started_at or _now()
    run.finished_at = None
    run.error_message = None
    run.artifacts = {}
    run.stages = initial_stages()
    db.commit()

    try:
        metadata = initialize_run_metadata(run, run_root)
        manifest_path = metadata["manifest"]
        _merge_artifacts(run, "metadata", metadata)
        db.commit()

        inputs = _stage(db, run, "import", lambda: _prepare_inputs(db, run, run_root))
        _merge_artifacts(
            run,
            "inputs",
            {
                "files": list(inputs.paths),
                "user_mapping": inputs.user_mapping_path,
                "reverse_mapping": inputs.reverse_mapping_path,
            },
        )
        db.commit()

        mode = str((run.parameters or {}).get("mode", "full"))
        if mode == "dry-run":
            dates = resolve_analysis_dates(run, _available_input_dates(inputs.paths))
            write_run_config(metadata["run_config"], run, config, dates)
            for stage in ("features", "scoring", "explain", "metrics", "reports"):
                _skip_stage(run, stage)
            run.status = "completed"
            run.current_stage = None
            run.finished_at = _now()
            db.commit()
            finalize_manifest(
                manifest_path,
                run,
                run_root,
                config,
                status="completed",
                exit_code=0,
            )
            db.refresh(run)
            return run

        feature_paths = _stage(
            db,
            run,
            "features",
            lambda: build_features(list(inputs.paths), run_root / "features"),
        )
        _merge_artifacts(run, "features", feature_paths)
        dates = resolve_analysis_dates(run, available_feature_dates(feature_paths))
        write_run_config(metadata["run_config"], run, config, dates)
        db.commit()

        scored = _stage(db, run, "scoring", lambda: _score(feature_paths, dates, config))
        score_paths = _save_full_scores(run_root / "scores", scored)
        _merge_artifacts(run, "scores", score_paths)
        db.commit()

        _stage(
            db,
            run,
            "explain",
            lambda: _persist_anomalies(
                db,
                run,
                list(inputs.paths),
                inputs.user_mapping_path,
                feature_paths,
                scored,
                config,
            ),
        )

        if mode in METRICS_MODES:
            metric = _stage(
                db,
                run,
                "metrics",
                lambda: generate_proxy_metrics(
                    db,
                    run,
                    feature_paths,
                    scored,
                    config,
                    run_root / "metrics",
                ),
            )
            _merge_artifacts(run, "metrics", metric.result.get("artifacts", {}))
        else:
            _skip_stage(run, "metrics")

        if mode in REPORT_MODES:
            report_artifacts = _stage(
                db,
                run,
                "reports",
                lambda: _generate_reports(db, run, scored, config, run_root),
            )
            _merge_artifacts(run, "reports", report_artifacts)
        else:
            _skip_stage(run, "reports")

        run.status = "completed"
        run.current_stage = None
        run.finished_at = _now()
        db.commit()
        finalize_manifest(
            manifest_path,
            run,
            run_root,
            config,
            status="completed",
            exit_code=0,
        )
        db.refresh(run)
        return run
    except Exception as exc:
        db.rollback()
        db.refresh(run)
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = _now()
        db.commit()
        if manifest_path is not None:
            finalize_manifest(
                manifest_path,
                run,
                run_root,
                config,
                status="failed",
                exit_code=1,
                error=str(exc),
            )
        raise


def resolve_analysis_dates(run: AnalysisRun, available: list[str]) -> list[str]:
    dates = sorted(set(available))
    if not dates:
        raise PipelineError("No dates are available for analysis")
    if run.scope in {"day", "week", "month"}:
        target = run.target_date
        if not target or target not in dates:
            raise PipelineError(f"Target date {target or '<missing>'} is not available")
        if run.scope == "day":
            return [target]
        window = 7 if run.scope == "week" else 30
        index = dates.index(target)
        return dates[max(0, index - window + 1) : index + 1]
    if run.scope == "range":
        if not run.start_date or not run.end_date:
            raise PipelineError("A range run requires start_date and end_date")
        selected = [date for date in dates if run.start_date <= date <= run.end_date]
        if not selected:
            raise PipelineError("No available dates fall inside the requested range")
        return selected
    if run.scope == "all":
        return dates
    raise PipelineError(f"Unsupported analysis scope: {run.scope}")


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
        db.rollback()
        db.refresh(run)
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
    stages[name] = {
        **stages[name],
        "status": "skipped",
        "finished_at": _now().isoformat(),
    }
    run.stages = stages


def _prepare_inputs(db: Session, run: AnalysisRun, run_root: Path) -> AnalysisInputBundle:
    ids = [UUID(value) for value in run.upload_ids or []]
    selected = list(db.scalars(select(UploadedFile).where(UploadedFile.id.in_(ids))))
    by_id = {upload.id: upload for upload in selected}
    if len(by_id) != len(ids):
        raise PipelineError("One or more selected uploads do not exist")
    uploads = [by_id[upload_id] for upload_id in ids]
    for upload in uploads:
        if upload.status != "normalized" or not upload.normalization_result:
            raise PipelineError(f"Upload {upload.id} is not normalized")
    return prepare_analysis_inputs(uploads, run_root / "inputs")


def _score_config(run: AnalysisRun) -> ScoreConfig:
    parameters = run.parameters or {}
    return ScoreConfig(
        contamination=float(parameters.get("contamination", 0.05)),
        n_estimators=int(parameters.get("n_estimators", 300)),
        n_neighbors=int(parameters.get("n_neighbors", 20)),
        top_n=int(parameters.get("top_n", 30)),
        random_state=int(parameters.get("random_state", 42)),
        max_samples=parameters.get("max_samples", "auto"),
        top_features=int(parameters.get("top_features", 5)),
        top_pct=float(parameters.get("top_pct", 0.05)),
    )


def _score(
    feature_paths: dict[str, Path], dates: list[str], config: ScoreConfig
) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for kind, path in feature_paths.items():
        daily: list[pd.DataFrame] = []
        feature_dates = set(pd.read_csv(path, usecols=["date"], dtype=str)["date"])
        for target_date in dates:
            if target_date in feature_dates:
                daily.append(score_feature_file(path, target_date, config))
        if daily:
            results[kind] = pd.concat(daily, ignore_index=True)
    if not results:
        raise PipelineError("No feature rows exist for the requested dates")
    return results


def _save_full_scores(
    output_directory: Path, scored: dict[str, pd.DataFrame]
) -> dict[str, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for kind, frame in scored.items():
        path = output_directory / f"scores_{kind}_full.csv"
        frame.to_csv(path, index=False)
        paths[kind] = path
        for target_date, daily in frame.groupby("date"):
            daily_path = output_directory / f"scores_{kind}_{target_date}.csv"
            daily.to_csv(daily_path, index=False)
            paths[f"{kind}_{target_date}"] = daily_path
    return paths


def _persist_anomalies(
    db: Session,
    run: AnalysisRun,
    input_paths: list[Path],
    mapping_path: Path,
    feature_paths: dict[str, Path],
    scored: dict[str, pd.DataFrame],
    config: ScoreConfig,
) -> int:
    db.execute(delete(Anomaly).where(Anomaly.run_id == run.id))
    count = 0
    anomaly_directory = settings.analysis_directory / str(run.id) / "anomalies"
    anomaly_directory.mkdir(parents=True, exist_ok=True)
    context_builder = AnomalyContextBuilder(
        input_paths, load_reverse_mapping(mapping_path)
    )
    explanation_rows: list[dict[str, object]] = []

    for kind, scored_frame in scored.items():
        features = pd.read_csv(feature_paths[kind])
        output = anomaly_directory / f"anomalies_{kind}_full.csv"
        scored_frame.to_csv(output, index=False)
        _merge_artifacts(run, f"anomalies_{kind}", output)
        daily_outputs: dict[str, Path] = {}
        for target_date, daily in scored_frame.groupby("date"):
            daily_path = anomaly_directory / f"anomalies_{kind}_{target_date}.csv"
            daily.to_csv(daily_path, index=False)
            daily_outputs[str(target_date)] = daily_path
        _merge_artifacts(run, f"anomalies_{kind}_daily", daily_outputs)
        for _, row in scored_frame.iterrows():
            target_date = str(row["date"])
            total = int((scored_frame["date"].astype(str) == target_date).sum())
            explanations = explain_row(
                features, row, target_date, top_k=config.top_features
            )
            severity = severity_for_rank(int(row["rank_combined"]), total)
            leading = explanations[0]["feature_name"] if explanations else "combined score"
            entity_type = "user" if kind == "users" else "host"
            context = context_builder.build(entity_type, str(row["entity"]), target_date)
            context["scoring"] = {
                "isolation_forest_raw": float(row["score_isolation_forest"]),
                "isolation_forest_normalized": float(row["score_isolation_forest_norm"]),
                "isolation_forest_rank": int(row["rank_isolation_forest"]),
                "lof_raw": float(row["score_lof"]),
                "lof_normalized": float(row["score_lof_norm"]),
                "lof_rank": int(row["rank_lof"]),
                "combined_score": float(row["score_combined"]),
                "combined_rank": int(row["rank_combined"]),
            }
            anomaly = Anomaly(
                run_id=run.id,
                entity_type=entity_type,
                entity=str(row["entity"]),
                date=date.fromisoformat(target_date),
                severity=severity,
                score=float(row["score_combined"]),
                rank=int(row["rank_combined"]),
                score_isolation_forest=float(row["score_isolation_forest"]),
                score_isolation_forest_norm=float(row["score_isolation_forest_norm"]),
                rank_isolation_forest=int(row["rank_isolation_forest"]),
                score_lof=float(row["score_lof"]),
                score_lof_norm=float(row["score_lof_norm"]),
                rank_lof=int(row["rank_lof"]),
                score_combined=float(row["score_combined"]),
                rank_combined=int(row["rank_combined"]),
                summary=f"Unusual {leading} compared with historical baseline",
                context=context,
            )
            anomaly.explanations = [AnomalyExplanation(**item) for item in explanations]
            db.add(anomaly)
            for position, item in enumerate(explanations, start=1):
                explanation_rows.append(
                    {
                        "entity_type": entity_type,
                        "entity": row["entity"],
                        "date": target_date,
                        "severity": severity,
                        "rank_combined": row["rank_combined"],
                        "contributor_rank": position,
                        **item,
                    }
                )
            count += 1
    explanation_path = anomaly_directory / "explanations_full.csv"
    explanation_frame = pd.DataFrame(explanation_rows)
    explanation_frame.to_csv(explanation_path, index=False)
    _merge_artifacts(run, "explanations", explanation_path)
    explanation_daily: dict[str, Path] = {}
    if not explanation_frame.empty:
        for target_date, daily in explanation_frame.groupby("date"):
            daily_path = anomaly_directory / f"explanations_{target_date}.csv"
            daily.to_csv(daily_path, index=False)
            explanation_daily[str(target_date)] = daily_path
    _merge_artifacts(run, "explanations_daily", explanation_daily)
    db.commit()
    return count


def _generate_reports(
    db: Session,
    run: AnalysisRun,
    scored: dict[str, pd.DataFrame],
    config: ScoreConfig,
    run_root: Path,
) -> dict[str, object]:
    charts = generate_graphical_reports(
        scored, run_root / "reports" / "charts", top_pct=config.top_pct
    )
    report = generate_automatic_report(db, run)
    return {
        "charts": charts,
        "soc_markdown": report.markdown_path or "",
        "soc_pdf": report.pdf_path or "",
        "context_csv": report.context_csv_path or "",
        "report_id": str(report.id),
    }


def _available_input_dates(paths: tuple[Path, ...]) -> list[str]:
    dates: set[str] = set()
    for path in paths:
        frame = pd.read_csv(path, dtype=str, usecols=lambda column: column in {"Date", "Timestamp"})
        if "Date" in frame:
            values = pd.to_datetime(frame["Date"], errors="coerce")
        elif "Timestamp" in frame:
            values = pd.to_datetime(frame["Timestamp"], errors="coerce")
        else:
            continue
        dates.update(values.dt.strftime("%Y-%m-%d").dropna().tolist())
    return sorted(dates)


def _merge_artifacts(run: AnalysisRun, key: str, value) -> None:
    artifacts = dict(run.artifacts or {})
    artifacts[key] = _artifact_value(value)
    run.artifacts = artifacts


def _artifact_value(value):
    if isinstance(value, dict):
        return {name: _artifact_value(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_artifact_value(item) for item in value]
    return str(value)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
