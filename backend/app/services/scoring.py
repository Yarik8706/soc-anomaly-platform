from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ScoreConfig:
    contamination: float = 0.05
    n_estimators: int = 300
    n_neighbors: int = 20
    top_n: int = 30
    random_state: int = 42


def score_feature_file(
    path: Path, target_date: str | None, config: ScoreConfig
) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if not {"entity", "date"}.issubset(frame.columns):
        raise ScoringError(f"{path.name} has no entity/date columns")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["date"])
    if frame.empty:
        raise ScoringError(f"{path.name} has no valid dated feature rows")

    selected_date = date.fromisoformat(target_date) if target_date else frame["date"].max()
    test = frame[frame["date"] == selected_date].copy()
    if test.empty:
        raise ScoringError(f"No feature rows found for {selected_date}")
    train = frame[frame["date"] != selected_date].copy()
    if train.empty:
        train = frame.copy()

    columns = [column for column in frame if column not in {"entity", "date"}]
    train_x = _matrix(train, columns)
    test_x = _matrix(test, columns)
    contamination = min(max(config.contamination, 0.001), 0.5)

    isolation = Pipeline(
        [
            ("scale", RobustScaler()),
            (
                "model",
                IsolationForest(
                    contamination=contamination,
                    n_estimators=config.n_estimators,
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
                        contamination=contamination,
                        novelty=True,
                    ),
                ),
            ]
        )
        lof.fit(train_x)
        lof_score = -lof.decision_function(test_x)
    else:
        lof_score = np.zeros(len(test_x))

    result = test[["entity", "date", *columns]].copy()
    result["score_isolation_forest"] = isolation_score
    result["score_lof"] = lof_score
    result["score"] = (_normalize(isolation_score) + _normalize(lof_score)) / 2
    result["rank"] = result["score"].rank(ascending=False, method="first").astype(int)
    result = result.sort_values("rank").head(config.top_n).reset_index(drop=True)
    return result


def _matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce").fillna(0)
    return numeric.to_numpy(dtype=float)


def _normalize(values: np.ndarray) -> np.ndarray:
    low, high = float(values.min()), float(values.max())
    if high == low:
        return np.zeros_like(values, dtype=float)
    return (values - low) / (high - low)
