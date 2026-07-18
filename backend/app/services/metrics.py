from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly, AnomalyExplanation
from app.models.report import ProxyMetric
from app.services.explanations import severity_for_rank
from app.services.scoring import ScoreConfig, score_feature_frame


def generate_proxy_metrics(
    db: Session,
    run: AnalysisRun,
    feature_paths: dict[str, Path],
    scored: dict[str, pd.DataFrame],
    config: ScoreConfig,
    output_directory: Path,
) -> ProxyMetric:
    """Calculate full-distribution proxy metrics and hyperparameter stability."""
    output_directory.mkdir(parents=True, exist_ok=True)
    parameters = run.parameters or {}
    ks = sorted({int(value) for value in parameters.get("k_values", [5, 10, 20]) if int(value) > 0})
    distribution_statistics: dict[str, dict[str, float | int]] = {}
    score_distributions: dict[str, dict[str, list[float] | list[int]]] = {}
    stability_summary: dict[str, dict[str, object]] = {}
    stability_records: dict[str, list[dict[str, object]]] = {}
    stability_dates: dict[str, list[str]] = {}
    distribution_rows: list[dict[str, object]] = []
    all_stability: list[pd.DataFrame] = []
    artifacts: dict[str, str] = {}

    for kind, frame in scored.items():
        entity_type = "user" if kind == "users" else "host"
        enriched = _with_severity(frame)
        summary = _distribution_summary(enriched)
        distribution_statistics[entity_type] = summary
        score_distributions[entity_type] = _distribution(enriched["score_combined"].tolist())
        distribution_rows.append({"entity_type": entity_type, **summary})

        features = pd.read_csv(feature_paths[kind])
        dates = sorted(enriched["date"].astype(str).unique().tolist())
        experiment_dates = dates if parameters.get("stability_all_dates") else dates[-1:]
        stability_dates[entity_type] = experiment_dates
        stability = _stability_experiments(
            features,
            enriched,
            experiment_dates,
            config,
            ks,
            parameters,
            entity_type,
        )
        stability_records[entity_type] = stability.to_dict(orient="records")
        all_stability.append(stability)
        stability_summary[entity_type] = _summarize_stability(stability, ks)

        hist_path = output_directory / f"score_hist_{kind}.png"
        _save_histogram(enriched, hist_path, f"Combined anomaly score — {kind}")
        artifacts[f"score_hist_{kind}"] = str(hist_path)
        stability_path = output_directory / f"stability_{kind}.png"
        _save_stability_chart(stability, stability_path, f"Model stability — {kind}", max(ks))
        artifacts[f"stability_{kind}_png"] = str(stability_path)

    for entity_type in ("user", "host"):
        distribution_statistics.setdefault(
            entity_type, _summary_from_values([], [])
        )
        score_distributions.setdefault(
            entity_type, {"bin_edges": [], "counts": []}
        )
        stability_summary.setdefault(
            entity_type,
            {
                "compared_run": None,
                "jaccard_at_k": None,
                "overlap_at_k": None,
                "spearman_at_k": None,
                "by_k": {},
            },
        )
        stability_records.setdefault(entity_type, [])
        stability_dates.setdefault(entity_type, [])

    explanations = _explainability_statistics(db, run)
    contributors = explanations.pop("feature_counts")
    explain_path = output_directory / "explainability_statistics.csv"
    pd.DataFrame(explanations.pop("feature_rows")).to_csv(explain_path, index=False)
    artifacts["explainability_csv"] = str(explain_path)

    proxy_path = output_directory / "proxy_metrics.csv"
    stability_path = output_directory / "stability.csv"
    pd.DataFrame(distribution_rows).to_csv(proxy_path, index=False)
    stability_frame = (
        pd.concat(all_stability, ignore_index=True) if all_stability else pd.DataFrame()
    )
    stability_frame.to_csv(stability_path, index=False)
    artifacts["proxy_metrics_csv"] = str(proxy_path)
    artifacts["stability_csv"] = str(stability_path)

    result: dict[str, object] = {
        "run_id": str(run.id),
        "generated_at": _now().isoformat(),
        "score_distributions": score_distributions,
        "distribution_statistics": distribution_statistics,
        "stability": stability_summary,
        "stability_experiments": stability_records,
        "stability_dates": stability_dates,
        "explainability": explanations,
        "contributing_features": contributors,
        "k_values": ks,
        "artifacts": artifacts,
    }
    json_path = output_directory / "proxy_metrics.json"
    artifacts["proxy_metrics_json"] = str(json_path)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    metric = db.scalar(select(ProxyMetric).where(ProxyMetric.run_id == run.id))
    if metric is None:
        metric = ProxyMetric(run_id=run.id, result=result)
        db.add(metric)
    else:
        metric.result = result
    db.commit()
    db.refresh(metric)
    return metric


def get_proxy_metrics(db: Session, run: AnalysisRun) -> ProxyMetric:
    cached = db.scalar(select(ProxyMetric).where(ProxyMetric.run_id == run.id))
    if cached:
        return cached

    # Compatibility fallback for historical runs that predate persisted full score files.
    current = list(db.scalars(select(Anomaly).where(Anomaly.run_id == run.id)).all())
    previous_run = db.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.status == "completed",
            AnalysisRun.id != run.id,
            AnalysisRun.created_at < run.created_at,
        )
        .order_by(AnalysisRun.created_at.desc())
    )
    previous = (
        list(db.scalars(select(Anomaly).where(Anomaly.run_id == previous_run.id)).all())
        if previous_run
        else []
    )
    distributions = {
        kind: _distribution([item.score for item in current if item.entity_type == kind])
        for kind in ("user", "host")
    }
    stability = {
        kind: _previous_run_stability(
            [item for item in current if item.entity_type == kind],
            [item for item in previous if item.entity_type == kind],
        )
        for kind in ("user", "host")
    }
    feature_rows = db.execute(
        select(AnomalyExplanation.feature_name)
        .join(Anomaly, Anomaly.id == AnomalyExplanation.anomaly_id)
        .where(Anomaly.run_id == run.id)
    )
    frequencies = Counter(str(name) for (name,) in feature_rows)
    result = {
        "run_id": str(run.id),
        "generated_at": _now().isoformat(),
        "score_distributions": distributions,
        "distribution_statistics": {
            kind: _summary_from_values(
                [item.score for item in current if item.entity_type == kind],
                [item.severity for item in current if item.entity_type == kind],
            )
            for kind in ("user", "host")
        },
        "stability": stability,
        "stability_experiments": {"user": [], "host": []},
        "explainability": {},
        "contributing_features": dict(frequencies.most_common()),
        "k_values": [20],
        "artifacts": {},
    }
    metric = ProxyMetric(run_id=run.id, result=result)
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def _with_severity(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["date"] = result["date"].astype(str)
    result["severity"] = result.groupby("date")["rank_combined"].transform(
        lambda ranks: [severity_for_rank(int(rank), len(ranks)) for rank in ranks]
    )
    return result


def _distribution_summary(frame: pd.DataFrame) -> dict[str, float | int]:
    return _summary_from_values(
        pd.to_numeric(frame["score_combined"], errors="coerce").fillna(0).tolist(),
        frame["severity"].astype(str).tolist(),
    )


def _summary_from_values(
    values: list[float], severities: list[str]
) -> dict[str, float | int]:
    scores = pd.Series(values, dtype=float)
    counts = Counter(severities)
    if scores.empty:
        mean = std = median = p90 = p95 = p99 = 0.0
    else:
        mean = float(scores.mean())
        std = float(scores.std(ddof=0)) if len(scores) > 1 else 0.0
        median = float(scores.median())
        p90, p95, p99 = (float(scores.quantile(value)) for value in (0.90, 0.95, 0.99))
    tail_gap = p95 - median
    tail_ratio = p95 / median if abs(median) > 1e-12 else (0.0 if p95 == 0 else p95 / 1e-12)
    return {
        "count": int(len(scores)),
        "mean": mean,
        "std": std,
        "median": median,
        "p90": p90,
        "p95": p95,
        "p99": p99,
        "tail_gap": float(tail_gap),
        "tail_ratio": float(tail_ratio),
        **{f"severity_{name}": int(counts.get(name, 0)) for name in ("critical", "high", "medium", "low")},
    }


def _distribution(scores: list[float], bins: int = 10) -> dict[str, list[float] | list[int]]:
    if not scores:
        return {"bin_edges": [], "counts": []}
    counts, edges = np.histogram(scores, bins=min(bins, max(1, len(scores))))
    return {"bin_edges": edges.tolist(), "counts": counts.astype(int).tolist()}


def _variant_configs(
    base: ScoreConfig, parameters: dict[str, object]
) -> list[tuple[str, str, object, ScoreConfig]]:
    contamination_grid = parameters.get("contamination_grid") or [
        max(0.001, base.contamination * 0.6),
        base.contamination,
        min(0.5, base.contamination * 1.4),
    ]
    neighbors_grid = parameters.get("n_neighbors_grid") or [
        max(1, base.n_neighbors // 2),
        base.n_neighbors,
        base.n_neighbors + max(1, base.n_neighbors // 2),
    ]
    estimator_grid = [max(10, base.n_estimators // 2), base.n_estimators, min(5_000, base.n_estimators * 2)]
    max_samples_grid: list[str | int | float] = [base.max_samples]
    alternative: str | int | float = 0.5 if base.max_samples == "auto" else "auto"
    if alternative != base.max_samples:
        max_samples_grid.append(alternative)
    random_grid = [base.random_state, base.random_state + 1]
    groups: list[tuple[str, str, list[object]]] = [
        ("contamination", "contamination", list(contamination_grid)),
        ("n_neighbors", "n_neighbors", list(neighbors_grid)),
        ("n_estimators", "n_estimators", list(estimator_grid)),
        ("max_samples", "max_samples", list(max_samples_grid)),
        ("random_state", "random_state", list(random_grid)),
    ]
    variants: list[tuple[str, str, object, ScoreConfig]] = []
    for group, field, raw_values in groups:
        for value in dict.fromkeys(raw_values):
            variants.append((group, field, value, replace(base, **{field: value})))
    return variants


def _stability_experiments(
    features: pd.DataFrame,
    base_scores: pd.DataFrame,
    dates: list[str],
    config: ScoreConfig,
    ks: list[int],
    parameters: dict[str, object],
    entity_type: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    base_by_date = {date: frame for date, frame in base_scores.groupby("date")}
    for group, parameter_name, value, variant in _variant_configs(config, parameters):
        for target_date in dates:
            alternative = score_feature_frame(features, target_date, variant)
            base = base_by_date[target_date]
            for k in ks:
                base_top = _top_entities(base, k)
                alternative_top = _top_entities(alternative, k)
                rows.append(
                    {
                        "date": target_date,
                        "entity_type": entity_type,
                        "parameter_group": group,
                        "parameter_name": parameter_name,
                        "parameter_value": value,
                        "k": k,
                        "jaccard": _jaccard(base_top, alternative_top),
                        "overlap": _overlap(base_top, alternative_top, k),
                        "spearman": _spearman(base, alternative, k),
                    }
                )
    return pd.DataFrame(rows)


def _top_entities(frame: pd.DataFrame, k: int) -> list[str]:
    return (
        frame.sort_values(["rank_combined", "entity"], kind="mergesort")
        .head(k)["entity"]
        .astype(str)
        .tolist()
    )


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def _overlap(left: list[str], right: list[str], k: int) -> float:
    return len(set(left) & set(right)) / max(k, 1)


def _spearman(left: pd.DataFrame, right: pd.DataFrame, k: int) -> float:
    left_rank = {entity: rank for rank, entity in enumerate(_top_entities(left, k), start=1)}
    right_rank = {entity: rank for rank, entity in enumerate(_top_entities(right, k), start=1)}
    entities = sorted(set(left_rank) | set(right_rank))
    if not entities:
        return 0.0
    if len(entities) == 1:
        return 1.0
    left_values = pd.Series([left_rank.get(entity, k + 1) for entity in entities], dtype=float)
    right_values = pd.Series([right_rank.get(entity, k + 1) for entity in entities], dtype=float)
    value = left_values.corr(right_values, method="spearman")
    return 0.0 if pd.isna(value) else float(value)


def _summarize_stability(frame: pd.DataFrame, ks: list[int]) -> dict[str, object]:
    if frame.empty:
        return {
            "compared_run": None,
            "jaccard_at_k": None,
            "overlap_at_k": None,
            "spearman_at_k": None,
            "by_k": {},
        }
    by_k: dict[str, dict[str, float]] = {}
    for k in ks:
        sample = frame[frame["k"] == k]
        by_k[str(k)] = {
            metric: float(pd.to_numeric(sample[metric], errors="coerce").fillna(0).mean())
            for metric in ("jaccard", "overlap", "spearman")
        }
    selected = by_k[str(max(ks))]
    return {
        "compared_run": "hyperparameter-grid",
        "jaccard_at_k": selected["jaccard"],
        "overlap_at_k": selected["overlap"],
        "spearman_at_k": selected["spearman"],
        "by_k": by_k,
    }


def _explainability_statistics(db: Session, run: AnalysisRun) -> dict[str, object]:
    rows = db.execute(
        select(
            AnomalyExplanation.feature_name,
            AnomalyExplanation.contribution,
            Anomaly.entity_type,
            Anomaly.severity,
        )
        .join(Anomaly, Anomaly.id == AnomalyExplanation.anomaly_id)
        .where(Anomaly.run_id == run.id)
    ).all()
    feature_counts = Counter(str(row.feature_name) for row in rows)
    values = np.asarray([abs(float(row.contribution)) for row in rows], dtype=float)
    feature_rows = [
        {"feature": feature, "count": count, "share": count / max(len(rows), 1)}
        for feature, count in feature_counts.most_common()
    ]
    return {
        "total_explanations": len(rows),
        "unique_features": len(feature_counts),
        "mean_abs_contribution": float(values.mean()) if values.size else 0.0,
        "median_abs_contribution": float(np.median(values)) if values.size else 0.0,
        "p95_abs_contribution": float(np.quantile(values, 0.95)) if values.size else 0.0,
        "critical_high_explanations": sum(
            1 for row in rows if str(row.severity) in {"critical", "high"}
        ),
        "feature_counts": dict(feature_counts.most_common()),
        "feature_rows": feature_rows,
    }


def _save_histogram(frame: pd.DataFrame, path: Path, title: str) -> None:
    values = pd.to_numeric(frame["score_combined"], errors="coerce").fillna(0).to_numpy()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(values, bins=min(20, max(5, int(math.sqrt(max(len(values), 1))))), color="#2563eb")
    ax.axvline(float(np.quantile(values, 0.95)), color="#db2777", linestyle="--", label="p95")
    ax.set(title=title, xlabel="Combined score", ylabel="Entities")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _save_stability_chart(frame: pd.DataFrame, path: Path, title: str, k: int) -> None:
    summary = frame[frame["k"] == k].groupby("parameter_group")[["jaccard", "overlap", "spearman"]].mean()
    fig, ax = plt.subplots(figsize=(10, 5))
    summary.plot(kind="bar", ax=ax, color=["#2563eb", "#d4a72c", "#db2777"])
    ax.set(title=f"{title} (K={k})", xlabel="Parameter", ylabel="Mean stability", ylim=(0, 1))
    ax.tick_params(axis="x", rotation=25)
    ax.legend(frameon=False, ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def _previous_run_stability(current: list[Anomaly], previous: list[Anomaly], k: int = 20):
    if not current or not previous:
        return {"compared_run": None, "jaccard_at_k": None, "overlap_at_k": None, "spearman_at_k": None}
    current_top = sorted(current, key=lambda item: item.rank)[:k]
    previous_top = sorted(previous, key=lambda item: item.rank)[:k]
    current_ranks = {item.entity: item.rank for item in current_top}
    previous_ranks = {item.entity: item.rank for item in previous_top}
    common = sorted(set(current_ranks) & set(previous_ranks))
    union = set(current_ranks) | set(previous_ranks)
    jaccard = len(common) / len(union) if union else 0.0
    overlap = len(common) / min(len(current_ranks), len(previous_ranks))
    if len(common) >= 2:
        left = pd.Series([current_ranks[name] for name in common], dtype=float)
        right = pd.Series([previous_ranks[name] for name in common], dtype=float)
        corr = left.corr(right, method="spearman")
        spearman = None if pd.isna(corr) else float(corr)
    else:
        spearman = None
    return {
        "compared_run": str(previous_top[0].run_id),
        "jaccard_at_k": jaccard,
        "overlap_at_k": overlap,
        "spearman_at_k": spearman,
    }


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
