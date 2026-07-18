from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.models.analysis_run import AnalysisRun
from app.services.scoring import ScoreConfig


def initialize_run_metadata(run: AnalysisRun, run_root: Path) -> dict[str, Path]:
    meta = run_root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    requested_path = meta / "requested_run.json"
    config_path = meta / "run_config.json"
    manifest_path = meta / "manifest.json"
    requested = {
        "run_id": str(run.id),
        "scope": run.scope,
        "target_date": run.target_date,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "parameters": run.parameters or {},
        "upload_ids": run.upload_ids or [],
        "requested_at": _iso(run.created_at),
    }
    _write_json(requested_path, requested)
    _write_json(config_path, {"status": "resolving", "requested": requested})
    _write_json(
        manifest_path,
        {
            "run_id": str(run.id),
            "run_tag": _run_tag(run),
            "status": "running",
            "exit_code": None,
            "started_at": _iso(run.started_at),
            "finished_at": None,
            "parameters": run.parameters or {},
            "model_configuration": {},
            "artifacts": [],
        },
    )
    return {
        "requested_run": requested_path,
        "run_config": config_path,
        "manifest": manifest_path,
    }


def write_run_config(
    path: Path,
    run: AnalysisRun,
    score_config: ScoreConfig,
    analysis_dates: list[str],
) -> None:
    payload = {
        "run_id": str(run.id),
        "run_tag": _run_tag(run),
        "scope": run.scope,
        "analysis_dates": analysis_dates,
        "mode": (run.parameters or {}).get("mode", "full"),
        "model_configuration": score_config.to_dict(),
        "preprocessing": {
            "scaler": "sklearn.preprocessing.RobustScaler",
            "numeric_coercion": "invalid and missing values replaced with 0",
            "training_split": "all dates except the scored date; all rows for a single-day dataset",
            "score_normalization": "per-day min-max",
            "feature_builder": "separate SIEM/PAN daily aggregation v2",
        },
        "algorithm_versions": _versions(),
        "requested": {
            "target_date": run.target_date,
            "start_date": run.start_date,
            "end_date": run.end_date,
            "upload_ids": run.upload_ids or [],
            "parameters": run.parameters or {},
        },
    }
    _write_json(path, payload)


def finalize_manifest(
    path: Path,
    run: AnalysisRun,
    run_root: Path,
    score_config: ScoreConfig,
    *,
    status: str,
    exit_code: int,
    error: str | None = None,
) -> None:
    run_config_path = path.parent / "run_config.json"
    try:
        resolved_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        resolved_config = {}
    artifacts = [str(path.relative_to(run_root))] + [
        str(candidate.relative_to(run_root))
        for candidate in sorted(run_root.rglob("*"))
        if candidate.is_file() and candidate != path
    ]
    payload = {
        "run_id": str(run.id),
        "run_tag": _run_tag(run),
        "scope": run.scope,
        "target_date": run.target_date,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "analysis_dates": resolved_config.get("analysis_dates", []),
        "status": status,
        "exit_code": exit_code,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "parameters": run.parameters or {},
        "model_configuration": score_config.to_dict(),
        "algorithm_versions": _versions(),
        "artifacts": artifacts,
        "error": error,
    }
    _write_json(path, payload)


def _versions() -> dict[str, str]:
    packages = ("numpy", "pandas", "scikit-learn")
    found: dict[str, str] = {"python": platform.python_version()}
    for package in packages:
        try:
            found[package] = version(package)
        except PackageNotFoundError:
            found[package] = "not-installed"
    return found


def _run_tag(run: AnalysisRun) -> str:
    requested = str((run.parameters or {}).get("run_tag") or "").strip()
    if requested:
        return requested
    anchor = run.target_date or run.end_date or run.start_date or "all"
    created = run.created_at.strftime("%Y%m%dT%H%M%S")
    return f"{run.scope}__{anchor}__{created}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")
