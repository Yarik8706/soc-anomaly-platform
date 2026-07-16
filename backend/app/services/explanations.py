from __future__ import annotations

import math

import pandas as pd


def explain_row(
    all_features: pd.DataFrame,
    row: pd.Series,
    target_date: str,
    top_k: int = 5,
) -> list[dict[str, float | str]]:
    columns = [column for column in all_features if column not in {"entity", "date"}]
    historical = all_features[
        pd.to_datetime(all_features["date"]).dt.strftime("%Y-%m-%d") != target_date
    ]
    entity_history = historical[historical["entity"] == row["entity"]]
    baseline_frame = entity_history if not entity_history.empty else historical
    if baseline_frame.empty:
        baseline_frame = all_features

    explanations = []
    for column in columns:
        values = pd.to_numeric(baseline_frame[column], errors="coerce").fillna(0)
        value = float(pd.to_numeric(pd.Series([row[column]]), errors="coerce").fillna(0).iloc[0])
        baseline = float(values.median())
        mad = float((values - baseline).abs().median())
        scale = 1.4826 * mad
        if not math.isfinite(scale) or scale == 0:
            scale = float(values.std())
        if not math.isfinite(scale) or scale == 0:
            scale = 1.0
        contribution = (value - baseline) / scale
        if math.isfinite(contribution):
            explanations.append(
                {
                    "feature_name": column,
                    "feature_value": value,
                    "baseline_value": baseline,
                    "contribution": contribution,
                }
            )
    return sorted(explanations, key=lambda item: abs(float(item["contribution"])), reverse=True)[:top_k]


def severity_for_rank(rank: int, total: int) -> str:
    percentile = rank / max(total, 1)
    if percentile <= 0.05:
        return "critical"
    if percentile <= 0.20:
        return "high"
    if percentile <= 0.50:
        return "medium"
    return "low"
