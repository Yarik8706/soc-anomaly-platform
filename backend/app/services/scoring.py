from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler


class ScoringError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScoreConfig:
    contamination: float = 0.05
    n_estimators: int = 300
    n_neighbors: int = 20
    top_n: int = 30
    random_state: int = 42
    max_samples: str | int | float = "auto"
    top_features: int = 5
    top_pct: float = 0.05

    def __post_init__(self) -> None:
        if not 0 < self.contamination <= 0.5:
            raise ValueError("contamination must be in (0, 0.5]")
        if self.n_estimators < 1 or self.n_neighbors < 1:
            raise ValueError("n_estimators and n_neighbors must be positive")
        if self.top_n < 1 or self.top_features < 1 or not 0 < self.top_pct <= 1:
            raise ValueError("top_n/top_features must be positive and top_pct must be in (0, 1]")
        if isinstance(self.max_samples, str) and self.max_samples != "auto":
            raise ValueError("max_samples string value must be 'auto'")
        if isinstance(self.max_samples, int) and self.max_samples < 1:
            raise ValueError("integer max_samples must be positive")
        if isinstance(self.max_samples, float) and not 0 < self.max_samples <= 1:
            raise ValueError("float max_samples must be in (0, 1]")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def score_feature_file(
    path: Path, target_date: str | None, config: ScoreConfig
) -> pd.DataFrame:
    frame = pd.read_csv(path)
    return score_feature_frame(frame, target_date, config, source_name=path.name)


def score_feature_frame(
    frame: pd.DataFrame,
    target_date: str | None,
    config: ScoreConfig,
    *,
    source_name: str = "features",
) -> pd.DataFrame:
    """Score every entity on one day; display limits are intentionally not applied."""
    if not {"entity", "date"}.issubset(frame.columns):
        raise ScoringError(f"{source_name} has no entity/date columns")
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    data = data.dropna(subset=["date"])
    if data.empty:
        raise ScoringError(f"{source_name} has no valid dated feature rows")

    selected_date = date.fromisoformat(target_date) if target_date else data["date"].max()
    test = data[data["date"] == selected_date].copy()
    if test.empty:
        raise ScoringError(f"No feature rows found for {selected_date}")
    train = data[data["date"] != selected_date].copy()
    if train.empty:
        train = data.copy()

    columns = [column for column in data if column not in {"entity", "date"}]
    if not columns:
        raise ScoringError(f"{source_name} has no numeric feature columns")
    train_x = _matrix(train, columns)
    test_x = _matrix(test, columns)

    isolation = Pipeline(
        [
            ("scale", RobustScaler()),
            (
                "model",
                IsolationForest(
                    contamination=config.contamination,
                    n_estimators=config.n_estimators,
                    max_samples=config.max_samples,
                    random_state=config.random_state,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    isolation.fit(train_x)
    isolation_score = -isolation.decision_function(test_x)

    if len(train_x) >= 2:
        neighbors = max(1, min(config.n_neighbors, len(train_x) - 1))
        lof = Pipeline(
            [
                ("scale", RobustScaler()),
                (
                    "model",
                    LocalOutlierFactor(
                        n_neighbors=neighbors,
                        contamination=config.contamination,
                        novelty=True,
                        metric="minkowski",
                        p=2,
                    ),
                ),
            ]
        )
        lof.fit(train_x)
        lof_score = -lof.decision_function(test_x)
    else:
        lof_score = np.zeros(len(test_x), dtype=float)

    isolation_norm = _normalize(isolation_score)
    lof_norm = _normalize(lof_score)
    combined = (isolation_norm + lof_norm) / 2.0

    result = test[["entity", "date", *columns]].copy()
    result["date"] = result["date"].astype(str)
    result["score_isolation_forest"] = isolation_score
    result["score_isolation_forest_norm"] = isolation_norm
    result["rank_isolation_forest"] = _rank(isolation_score)
    result["score_lof"] = lof_score
    result["score_lof_norm"] = lof_norm
    result["rank_lof"] = _rank(lof_score)
    result["score_combined"] = combined
    result["score_combined_norm"] = combined
    result["rank_combined"] = _rank(combined)
    # Backwards-compatible API/DB aliases.
    result["score"] = result["score_combined"]
    result["rank"] = result["rank_combined"]
    return result.sort_values(
        ["rank_combined", "rank_isolation_forest", "rank_lof", "entity"],
        kind="mergesort",
    ).reset_index(drop=True)


def _matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce").fillna(0)
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        values[~np.isfinite(values)] = 0.0
    return values


def _normalize(values: np.ndarray) -> np.ndarray:
    low, high = float(values.min()), float(values.max())
    if not np.isfinite(low) or not np.isfinite(high) or high == low:
        return np.zeros_like(values, dtype=float)
    return (values - low) / (high - low)


def _rank(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(ascending=False, method="first").astype(int).to_numpy()
