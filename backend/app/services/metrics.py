from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.anomaly import Anomaly, AnomalyExplanation
from app.models.report import ProxyMetric


def get_proxy_metrics(db: Session, run: AnalysisRun) -> ProxyMetric:
    cached = db.scalar(select(ProxyMetric).where(ProxyMetric.run_id == run.id))
    if cached:
        return cached

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
        kind: _stability(
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
        "stability": stability,
        "contributing_features": dict(frequencies.most_common()),
    }
    metric = ProxyMetric(run_id=run.id, result=result)
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def _distribution(scores: list[float], bins: int = 10) -> dict[str, list[float] | list[int]]:
    if not scores:
        return {"bin_edges": [], "counts": []}
    counts, edges = np.histogram(scores, bins=min(bins, max(1, len(scores))))
    return {"bin_edges": edges.tolist(), "counts": counts.astype(int).tolist()}


def _stability(current: list[Anomaly], previous: list[Anomaly], k: int = 20):
    if not current or not previous:
        return {"compared_run": None, "jaccard_at_k": None, "overlap_at_k": None, "spearman_at_k": None}
    current_top = sorted(current, key=lambda item: item.rank)[:k]
    previous_top = sorted(previous, key=lambda item: item.rank)[:k]
    current_ranks = {item.entity: item.rank for item in current_top}
    previous_ranks = {item.entity: item.rank for item in previous_top}
    current_set, previous_set = set(current_ranks), set(previous_ranks)
    common = sorted(current_set & previous_set)
    union = current_set | previous_set
    jaccard = len(common) / len(union) if union else 0.0
    overlap = len(common) / min(len(current_set), len(previous_set))
    if len(common) >= 2:
        left = np.array([current_ranks[name] for name in common], dtype=float)
        right = np.array([previous_ranks[name] for name in common], dtype=float)
        spearman = float(np.corrcoef(_ranks(left), _ranks(right))[0, 1])
        if not np.isfinite(spearman):
            spearman = None
    else:
        spearman = None
    return {
        "compared_run": str(previous_top[0].run_id),
        "jaccard_at_k": jaccard,
        "overlap_at_k": overlap,
        "spearman_at_k": spearman,
    }


def _ranks(values: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(values)).astype(float)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
