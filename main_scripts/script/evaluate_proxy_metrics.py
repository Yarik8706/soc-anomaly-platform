#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluate_proxy_metrics.py

Модуль экспериментальной оценки качества безнадзорной модели обнаружения аномалий
в условиях отсутствия эталонной разметки.

Назначение:
- рассчитывает прокси-метрики качества для пользователей и хостов;
- анализирует распределение итогового score аномальности за выбранную дату;
- оценивает устойчивость верхней части ранга при небольшом изменении
  гиперпараметров модели;
- агрегирует признаки, чаще всего выступающие объяснением аномальности,
  на основе результатов explain_anomalies.py;
- сохраняет итоговые таблицы, JSON-резюме и графики, пригодные для включения
  в текст ВКР.

Ключевая идея:
В текущем проекте train_anomaly_models.py экспортирует только TOP-N аномалий,
поэтому для корректной оценки устойчивости и построения гистограмм данный
скрипт рассчитывает полный дневной скоринг напрямую через viz_core.score_day().
Это позволяет анализировать все сущности выбранного дня, а не только заранее
усечённый список.

Входные данные:
- features_users_clean.csv
- features_hosts_clean.csv
- (опционально) anomalies_users_YYYY-MM-DD_explain.csv
- (опционально) anomalies_hosts_YYYY-MM-DD_explain.csv

Выходные артефакты:
- proxy_metrics_users_YYYY-MM-DD.csv
- proxy_metrics_hosts_YYYY-MM-DD.csv
- stability_users_YYYY-MM-DD.csv
- stability_hosts_YYYY-MM-DD.csv
- contributors_users_YYYY-MM-DD.csv
- contributors_hosts_YYYY-MM-DD.csv
- proxy_metrics_summary_YYYY-MM-DD.json
- score_hist_users_YYYY-MM-DD.png
- score_hist_hosts_YYYY-MM-DD.png
- stability_contamination_users_YYYY-MM-DD.png
- stability_contamination_hosts_YYYY-MM-DD.png
- stability_neighbors_users_YYYY-MM-DD.png
- stability_neighbors_hosts_YYYY-MM-DD.png
- contributors_freq_users_YYYY-MM-DD.png
- contributors_freq_hosts_YYYY-MM-DD.png

Примеры запуска:
  python evaluate_proxy_metrics.py --work .\\features --date 2025-12-31
  python evaluate_proxy_metrics.py --work .\\features --date 2025-12-31 --out-dir .\\report\\metrics
  python evaluate_proxy_metrics.py --work .\\features --date 2025-12-31 --k-list 10,20
  python evaluate_proxy_metrics.py --work .\\features --date 2025-12-31 --strict-explain
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import viz_core as core


ID_COLS: list[str] = ["entity", "date"]
DEFAULT_SEVERITIES_FOR_CONTRIB: tuple[str, ...] = ("critical", "high")


@dataclass(frozen=True)
class ExperimentConfig:
    """Конфигурация одного запуска расчёта прокси-метрик.

    Атрибуты:
        work_dir: Директория с очищенными таблицами признаков.
        anomaly_dir: Директория с explain-файлами и иными артефактами аномалий.
        out_dir: Директория, куда сохраняются метрики и графики.
        target_date: Целевая дата расчёта в формате YYYY-MM-DD.
        contamination: Базовое значение contamination.
        n_estimators: Базовое число деревьев Isolation Forest.
        n_neighbors: Базовое значение числа соседей для LOF.
        random_state: Инициализирующее значение генератора случайных чисел.
        ks: Набор значений K для расчёта Jaccard@K, Overlap@K и Spearman@K.
        plot_k: Значение K, использующееся в графиках устойчивости.
        contamination_grid: Набор альтернативных значений contamination.
        neighbors_grid: Набор альтернативных значений n_neighbors.
        contributor_severities: Уровни severity, попадающие в анализ explainability.
        strict_explain: Если True, отсутствие explain-файлов считается ошибкой.
        save_score_tables: Если True, сохраняются полные дневные таблицы скоринга.
    """

    work_dir: Path
    anomaly_dir: Path
    out_dir: Path
    target_date: str
    contamination: float
    n_estimators: int
    n_neighbors: int
    random_state: int
    ks: tuple[int, ...]
    plot_k: int
    contamination_grid: tuple[float, ...]
    neighbors_grid: tuple[int, ...]
    contributor_severities: tuple[str, ...]
    strict_explain: bool
    save_score_tables: bool


def _parse_float_list(value: str) -> tuple[float, ...]:
    """Преобразует строку вида '0.03,0.05,0.07' в кортеж float.

    Args:
        value: Строковое представление списка чисел.

    Returns:
        Кортеж вещественных чисел.

    Raises:
        ValueError: Если список пуст или содержит некорректные элементы.
    """
    raw: list[str] = [item.strip() for item in str(value).split(",") if item.strip()]
    if not raw:
        raise ValueError("Ожидался непустой список вещественных значений.")
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item))
        except Exception as exc:
            raise ValueError(f"Не удалось преобразовать '{item}' к float.") from exc
    return tuple(out)


def _parse_int_list(value: str) -> tuple[int, ...]:
    """Преобразует строку вида '10,20' в кортеж int.

    Args:
        value: Строковое представление списка целых чисел.

    Returns:
        Кортеж целых чисел.

    Raises:
        ValueError: Если список пуст или содержит некорректные элементы.
    """
    raw: list[str] = [item.strip() for item in str(value).split(",") if item.strip()]
    if not raw:
        raise ValueError("Ожидался непустой список целых значений.")
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except Exception as exc:
            raise ValueError(f"Не удалось преобразовать '{item}' к int.") from exc
    return tuple(out)


def _normalize_date(value: str) -> str:
    """Нормализует дату к формату YYYY-MM-DD.

    Args:
        value: Исходная строка даты.

    Returns:
        Нормализованная строка даты.
    """
    return str(pd.to_datetime(value, errors="raise").date())


def _pick_latest_date(work_dir: Path) -> str:
    """Определяет последнюю доступную дату по таблицам признаков.

    Args:
        work_dir: Директория с очищенными признаками.

    Returns:
        Последняя доступная дата.
    """
    users: pd.DataFrame = core.load_features(work_dir, "users")
    hosts: pd.DataFrame = core.load_features(work_dir, "hosts")
    return core.pick_latest_date(users, hosts)


def _coerce_path(base_dir: Path, maybe_relative: str | None, default_name: str | None = None) -> Path:
    """Преобразует путь к абсолютному виду относительно базовой директории.

    Args:
        base_dir: Базовая директория для относительных путей.
        maybe_relative: Пользовательский путь.
        default_name: Имя директории по умолчанию, если путь не задан.

    Returns:
        Абсолютный или нормализованный путь.
    """
    if maybe_relative:
        path = Path(maybe_relative)
    elif default_name is not None:
        path = base_dir / default_name
    else:
        path = base_dir
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _build_config(args: argparse.Namespace) -> ExperimentConfig:
    """Формирует и валидирует конфигурацию запуска.

    Args:
        args: Распарсенные аргументы командной строки.

    Returns:
        Валидированная конфигурация эксперимента.

    Raises:
        FileNotFoundError: Если обязательные директории отсутствуют.
        ValueError: Если параметры содержат некорректные значения.
    """
    work_dir: Path = _coerce_path(Path.cwd(), args.work)
    if not work_dir.exists():
        raise FileNotFoundError(f"Директория признаков не найдена: {work_dir}")

    anomaly_dir: Path = _coerce_path(work_dir, args.anomaly_dir) if args.anomaly_dir else work_dir
    if not anomaly_dir.exists():
        raise FileNotFoundError(f"Директория аномалий не найдена: {anomaly_dir}")

    out_dir: Path = _coerce_path(work_dir.parent, args.out_dir, default_name="report/metrics")
    out_dir.mkdir(parents=True, exist_ok=True)

    target_date: str = _normalize_date(args.date) if args.date else _pick_latest_date(work_dir)

    ks: tuple[int, ...] = _parse_int_list(args.k_list)
    if any(k <= 0 for k in ks):
        raise ValueError("Все значения K должны быть положительными.")

    plot_k: int = int(args.plot_k)
    if plot_k <= 0:
        raise ValueError("plot_k должен быть положительным целым числом.")
    if plot_k not in ks:
        ks = tuple(sorted(set(ks + (plot_k,))))

    contamination_grid: tuple[float, ...] = _parse_float_list(args.contamination_grid)
    if any(not (0.0 < x <= 0.5) for x in contamination_grid):
        raise ValueError("Каждое значение contamination должно принадлежать интервалу (0, 0.5].")

    neighbors_grid: tuple[int, ...] = _parse_int_list(args.neighbors_grid)
    if any(x <= 0 for x in neighbors_grid):
        raise ValueError("Каждое значение n_neighbors должно быть положительным.")

    contributor_severities: tuple[str, ...] = tuple(
        item.strip().lower() for item in str(args.contributor_severities).split(",") if item.strip()
    )
    if not contributor_severities:
        contributor_severities = DEFAULT_SEVERITIES_FOR_CONTRIB

    if not (0.0 < float(args.contamination) <= 0.5):
        raise ValueError("Базовое contamination должно принадлежать интервалу (0, 0.5].")
    if int(args.n_estimators) <= 0:
        raise ValueError("n_estimators должен быть положительным.")
    if int(args.n_neighbors) <= 0:
        raise ValueError("n_neighbors должен быть положительным.")

    return ExperimentConfig(
        work_dir=work_dir,
        anomaly_dir=anomaly_dir,
        out_dir=out_dir,
        target_date=target_date,
        contamination=float(args.contamination),
        n_estimators=int(args.n_estimators),
        n_neighbors=int(args.n_neighbors),
        random_state=int(args.random_state),
        ks=tuple(sorted(set(ks))),
        plot_k=plot_k,
        contamination_grid=tuple(sorted(set(contamination_grid))),
        neighbors_grid=tuple(sorted(set(neighbors_grid))),
        contributor_severities=contributor_severities,
        strict_explain=bool(args.strict_explain),
        save_score_tables=bool(args.save_score_tables),
    )


def _read_explain_file(anomaly_dir: Path, kind: str, target_date: str) -> pd.DataFrame | None:
    """Читает explain-файл для указанного типа сущности, если он существует.

    Args:
        anomaly_dir: Директория с explain-файлами.
        kind: Тип сущности: users или hosts.
        target_date: Целевая дата.

    Returns:
        DataFrame с explain-данными либо None, если файл отсутствует.
    """
    path: Path = anomaly_dir / f"anomalies_{kind}_{target_date}_explain.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str, keep_default_na=True)


def _safe_numeric(series: pd.Series) -> pd.Series:
    """Преобразует Series к числовому типу с безопасной обработкой ошибок.

    Args:
        series: Исходная серия.

    Returns:
        Числовая серия.
    """
    return pd.to_numeric(series, errors="coerce")


def _top_k_entities(scores: pd.DataFrame, k: int) -> list[str]:
    """Возвращает список сущностей из верхней части ранга.

    Args:
        scores: Таблица скоринга за день.
        k: Размер верхней части ранга.

    Returns:
        Список идентификаторов сущностей в порядке убывания аномальности.
    """
    if scores.empty:
        return []
    df: pd.DataFrame = scores.sort_values(["rank_combined", "entity"], kind="mergesort").head(k)
    return df["entity"].astype(str).tolist()


def _rank_map(scores: pd.DataFrame, k: int) -> dict[str, int]:
    """Строит отображение сущность -> место в top-K.

    Args:
        scores: Таблица скоринга за день.
        k: Размер верхней части ранга.

    Returns:
        Словарь с позициями сущностей.
    """
    entities: list[str] = _top_k_entities(scores, k)
    return {entity: idx for idx, entity in enumerate(entities, start=1)}


def _jaccard_at_k(base_entities: Sequence[str], alt_entities: Sequence[str]) -> float:
    """Вычисляет Jaccard@K между двумя top-K списками.

    Args:
        base_entities: Базовый top-K список.
        alt_entities: Альтернативный top-K список.

    Returns:
        Коэффициент Жаккара.
    """
    base_set: set[str] = set(base_entities)
    alt_set: set[str] = set(alt_entities)
    union_size: int = len(base_set | alt_set)
    if union_size == 0:
        return 0.0
    return float(len(base_set & alt_set) / union_size)


def _overlap_at_k(base_entities: Sequence[str], alt_entities: Sequence[str], k: int) -> float:
    """Вычисляет Overlap@K между двумя top-K списками.

    Args:
        base_entities: Базовый top-K список.
        alt_entities: Альтернативный top-K список.
        k: Нормировочный размер списка.

    Returns:
        Доля совпадающих элементов в верхней части ранга.
    """
    if k <= 0:
        return 0.0
    base_set: set[str] = set(base_entities)
    alt_set: set[str] = set(alt_entities)
    return float(len(base_set & alt_set) / k)


def _spearman_at_k(base_scores: pd.DataFrame, alt_scores: pd.DataFrame, k: int) -> float:
    """Вычисляет Spearman@K по объединению сущностей из двух top-K списков.

    Логика расчёта:
    - строится объединение сущностей, вошедших хотя бы в один из двух top-K списков;
    - если сущность отсутствует в одном из списков, ей назначается штрафной ранг K + 1;
    - ранги сравниваются через ранговую корреляцию Спирмена.

    Args:
        base_scores: Базовая таблица скоринга.
        alt_scores: Альтернативная таблица скоринга.
        k: Размер верхней части ранга.

    Returns:
        Коэффициент ранговой корреляции Спирмена.
    """
    base_rank: dict[str, int] = _rank_map(base_scores, k)
    alt_rank: dict[str, int] = _rank_map(alt_scores, k)
    union_entities: list[str] = sorted(set(base_rank) | set(alt_rank))
    if not union_entities:
        return 0.0
    if len(union_entities) == 1:
        one: str = union_entities[0]
        return 1.0 if base_rank.get(one, k + 1) == alt_rank.get(one, k + 1) else 0.0

    base_values: list[int] = [base_rank.get(entity, k + 1) for entity in union_entities]
    alt_values: list[int] = [alt_rank.get(entity, k + 1) for entity in union_entities]

    corr: float = pd.Series(base_values, dtype=float).corr(pd.Series(alt_values, dtype=float), method="spearman")
    if pd.isna(corr):
        return 0.0
    return float(corr)


def _score_summary(scores: pd.DataFrame) -> dict[str, float | int]:
    """Формирует сводные статистики по распределению итогового score.

    Args:
        scores: Полная таблица дневного скоринга.

    Returns:
        Словарь агрегированных метрик.
    """
    score: pd.Series = _safe_numeric(scores["score_combined_norm"]).fillna(0)
    n_rows: int = int(len(score))
    if n_rows == 0:
        return {
            "rows_total": 0,
            "score_mean": 0.0,
            "score_std": 0.0,
            "score_median": 0.0,
            "score_p90": 0.0,
            "score_p95": 0.0,
            "score_p99": 0.0,
            "tail_gap_p95_median": 0.0,
            "tail_ratio_p95_median": 0.0,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
        }

    score_mean: float = float(score.mean())
    score_std: float = float(score.std(ddof=0)) if n_rows > 1 else 0.0
    score_median: float = float(score.median())
    score_p90: float = float(score.quantile(0.90))
    score_p95: float = float(score.quantile(0.95))
    score_p99: float = float(score.quantile(0.99))
    tail_gap: float = float(score_p95 - score_median)
    denom: float = score_median if abs(score_median) > 1e-12 else 1e-12
    tail_ratio: float = float(score_p95 / denom)

    counts: dict[str, int] = scores["severity"].astype(str).value_counts().to_dict()
    return {
        "rows_total": n_rows,
        "score_mean": score_mean,
        "score_std": score_std,
        "score_median": score_median,
        "score_p90": score_p90,
        "score_p95": score_p95,
        "score_p99": score_p99,
        "tail_gap_p95_median": tail_gap,
        "tail_ratio_p95_median": tail_ratio,
        "critical_count": int(counts.get("critical", 0)),
        "high_count": int(counts.get("high", 0)),
        "medium_count": int(counts.get("medium", 0)),
        "low_count": int(counts.get("low", 0)),
    }


def _run_scores_for_day(
    features_df: pd.DataFrame,
    target_date: str,
    contamination: float,
    n_estimators: int,
    n_neighbors: int,
    random_state: int,
) -> pd.DataFrame:
    """Рассчитывает полный дневной скоринг для выбранных параметров модели.

    Args:
        features_df: Полная таблица признаков по одному типу сущности.
        target_date: Целевая дата.
        contamination: Доля аномалий.
        n_estimators: Число деревьев Isolation Forest.
        n_neighbors: Число соседей LOF.
        random_state: Фиксация случайности.

    Returns:
        Полная таблица скоринга для выбранной даты.
    """
    return core.score_day(
        df=features_df,
        day=target_date,
        contamination=contamination,
        n_estimators=n_estimators,
        n_neighbors=n_neighbors,
        random_state=random_state,
    )


def _stability_against_contamination(
    base_scores: pd.DataFrame,
    features_df: pd.DataFrame,
    target_date: str,
    cfg: ExperimentConfig,
    entity_type: str,
) -> pd.DataFrame:
    """Считает устойчивость ранга при варьировании contamination.

    Args:
        base_scores: Базовый дневной скоринг.
        features_df: Таблица признаков выбранного типа сущности.
        target_date: Целевая дата.
        cfg: Конфигурация запуска.
        entity_type: Тип сущности: users или hosts.

    Returns:
        Таблица устойчивости по группе параметров contamination.
    """
    rows: list[dict[str, object]] = []
    for contamination in cfg.contamination_grid:
        alt_scores: pd.DataFrame = _run_scores_for_day(
            features_df=features_df,
            target_date=target_date,
            contamination=contamination,
            n_estimators=cfg.n_estimators,
            n_neighbors=cfg.n_neighbors,
            random_state=cfg.random_state,
        )
        for k in cfg.ks:
            base_top: list[str] = _top_k_entities(base_scores, k)
            alt_top: list[str] = _top_k_entities(alt_scores, k)
            rows.append(
                {
                    "date": target_date,
                    "entity_type": entity_type,
                    "param_group": "contamination",
                    "param_name": "contamination",
                    "param_value": float(contamination),
                    "k": int(k),
                    "jaccard": _jaccard_at_k(base_top, alt_top),
                    "overlap": _overlap_at_k(base_top, alt_top, k),
                    "spearman": _spearman_at_k(base_scores, alt_scores, k),
                }
            )
    return pd.DataFrame(rows)


def _stability_against_neighbors(
    base_scores: pd.DataFrame,
    features_df: pd.DataFrame,
    target_date: str,
    cfg: ExperimentConfig,
    entity_type: str,
) -> pd.DataFrame:
    """Считает устойчивость ранга при варьировании n_neighbors.

    Args:
        base_scores: Базовый дневной скоринг.
        features_df: Таблица признаков выбранного типа сущности.
        target_date: Целевая дата.
        cfg: Конфигурация запуска.
        entity_type: Тип сущности: users или hosts.

    Returns:
        Таблица устойчивости по группе параметров n_neighbors.
    """
    rows: list[dict[str, object]] = []
    for n_neighbors in cfg.neighbors_grid:
        alt_scores: pd.DataFrame = _run_scores_for_day(
            features_df=features_df,
            target_date=target_date,
            contamination=cfg.contamination,
            n_estimators=cfg.n_estimators,
            n_neighbors=n_neighbors,
            random_state=cfg.random_state,
        )
        for k in cfg.ks:
            base_top: list[str] = _top_k_entities(base_scores, k)
            alt_top: list[str] = _top_k_entities(alt_scores, k)
            rows.append(
                {
                    "date": target_date,
                    "entity_type": entity_type,
                    "param_group": "n_neighbors",
                    "param_name": "n_neighbors",
                    "param_value": int(n_neighbors),
                    "k": int(k),
                    "jaccard": _jaccard_at_k(base_top, alt_top),
                    "overlap": _overlap_at_k(base_top, alt_top, k),
                    "spearman": _spearman_at_k(base_scores, alt_scores, k),
                }
            )
    return pd.DataFrame(rows)


def _aggregate_contributors(
    explain_df: pd.DataFrame | None,
    contributor_severities: Iterable[str],
    strict_explain: bool,
    entity_type: str,
    target_date: str,
) -> pd.DataFrame:
    """Агрегирует частоты признаков, попадающих в top_contributors.

    Args:
        explain_df: Таблица explain-результатов либо None.
        contributor_severities: Уровни severity, попадающие в агрегацию.
        strict_explain: Если True, отсутствие explain-файла считается ошибкой.
        entity_type: Тип сущности: users или hosts.
        target_date: Целевая дата.

    Returns:
        Таблица частот признаков. Пустой DataFrame, если explain отсутствует и
        строгий режим отключён.

    Raises:
        FileNotFoundError: Если explain-файл отсутствует при strict_explain=True.
    """
    if explain_df is None:
        if strict_explain:
            raise FileNotFoundError(
                f"Не найден explain-файл для {entity_type} и даты {target_date}. "
                f"Перед запуском оценочных метрик необходимо выполнить explain_anomalies.py."
            )
        return pd.DataFrame(columns=["feature", "count", "share"])

    df: pd.DataFrame = explain_df.copy()
    if "severity" not in df.columns:
        return pd.DataFrame(columns=["feature", "count", "share"])

    keep: set[str] = {item.lower() for item in contributor_severities}
    df = df[df["severity"].astype(str).str.lower().isin(keep)].copy()
    if df.empty:
        return pd.DataFrame(columns=["feature", "count", "share"])

    feature_cols: list[str] = [
        col for col in df.columns if col.startswith("contrib") and col.endswith("_feature")
    ]
    if not feature_cols:
        return pd.DataFrame(columns=["feature", "count", "share"])

    series_list: list[pd.Series] = []
    for col in feature_cols:
        s: pd.Series = df[col].dropna().astype(str).str.strip()
        s = s[s != ""]
        if not s.empty:
            series_list.append(s)

    if not series_list:
        return pd.DataFrame(columns=["feature", "count", "share"])

    all_features: pd.Series = pd.concat(series_list, ignore_index=True)
    counts: pd.Series = all_features.value_counts()
    total: int = int(counts.sum())
    out: pd.DataFrame = counts.rename_axis("feature").reset_index(name="count")
    out["share"] = out["count"] / total if total > 0 else 0.0
    return out


def _mean_metric_for_group(stability_df: pd.DataFrame, param_group: str, k: int, metric: str) -> float:
    """Возвращает среднее значение метрики по группе параметров и фиксированному K.

    Args:
        stability_df: Таблица устойчивости.
        param_group: Имя группы параметров.
        k: Размер верхней части ранга.
        metric: Имя числового столбца.

    Returns:
        Среднее значение либо 0.0 при отсутствии строк.
    """
    df: pd.DataFrame = stability_df[
        (stability_df["param_group"].astype(str) == param_group) & (stability_df["k"].astype(int) == int(k))
    ]
    if df.empty:
        return 0.0
    series: pd.Series = _safe_numeric(df[metric]).dropna()
    return float(series.mean()) if not series.empty else 0.0


def _build_proxy_metrics_table(
    entity_type: str,
    target_date: str,
    score_summary: dict[str, float | int],
    stability_df: pd.DataFrame,
    contributor_df: pd.DataFrame,
    ks: Sequence[int],
) -> pd.DataFrame:
    """Строит итоговую сводную таблицу прокси-метрик по одному типу сущности.

    Args:
        entity_type: Тип сущности: users или hosts.
        target_date: Целевая дата.
        score_summary: Словарь метрик распределения score.
        stability_df: Таблица устойчивости.
        contributor_df: Таблица частот explain-признаков.
        ks: Набор значений K.

    Returns:
        Однострочный DataFrame со сводными метриками.
    """
    row: dict[str, object] = {
        "date": target_date,
        "entity_type": entity_type,
        **score_summary,
    }
    for k in ks:
        row[f"mean_jaccard_{k}_contamination"] = _mean_metric_for_group(stability_df, "contamination", k, "jaccard")
        row[f"mean_overlap_{k}_contamination"] = _mean_metric_for_group(stability_df, "contamination", k, "overlap")
        row[f"mean_spearman_{k}_contamination"] = _mean_metric_for_group(stability_df, "contamination", k, "spearman")
        row[f"mean_jaccard_{k}_neighbors"] = _mean_metric_for_group(stability_df, "n_neighbors", k, "jaccard")
        row[f"mean_overlap_{k}_neighbors"] = _mean_metric_for_group(stability_df, "n_neighbors", k, "overlap")
        row[f"mean_spearman_{k}_neighbors"] = _mean_metric_for_group(stability_df, "n_neighbors", k, "spearman")

    top_features: list[str] = contributor_df.head(5)["feature"].astype(str).tolist() if not contributor_df.empty else []
    row["top_contributor_features"] = "; ".join(top_features)
    return pd.DataFrame([row])


def _save_score_histogram(scores: pd.DataFrame, out_path: Path, title: str) -> None:
    """Сохраняет гистограмму распределения итогового score аномальности.

    Args:
        scores: Полная таблица дневного скоринга.
        out_path: Путь к PNG-файлу.
        title: Заголовок графика.
    """
    if scores.empty:
        return
    values: np.ndarray = _safe_numeric(scores["score_combined_norm"]).fillna(0).to_numpy(dtype=float)
    if values.size == 0:
        return
    threshold: float = float(np.quantile(values, 0.95))
    plt.figure()
    plt.hist(values, bins=min(20, max(5, int(math.sqrt(len(values))))))
    plt.axvline(threshold, linestyle="--")
    plt.xlabel("Нормированная комбинированная оценка аномальности")
    plt.ylabel("Количество сущностей")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def _save_stability_plot(
    stability_df: pd.DataFrame,
    out_path: Path,
    title: str,
    param_group: str,
    plot_k: int,
) -> None:
    """Сохраняет график устойчивости по выбранной группе параметров.

    На одном графике строятся линии:
    - Jaccard@plot_k
    - Overlap@plot_k
    - Spearman@plot_k

    Args:
        stability_df: Полная таблица устойчивости.
        out_path: Путь к PNG-файлу.
        title: Заголовок графика.
        param_group: Группа параметров: contamination или n_neighbors.
        plot_k: Значение K, отображаемое на графике.
    """
    df: pd.DataFrame = stability_df[
        (stability_df["param_group"].astype(str) == param_group) & (stability_df["k"].astype(int) == int(plot_k))
    ].copy()
    if df.empty:
        return
    df = df.sort_values("param_value", kind="mergesort")
    x: np.ndarray = _safe_numeric(df["param_value"]).fillna(0).to_numpy(dtype=float)
    plt.figure()
    plt.plot(x, _safe_numeric(df["jaccard"]).fillna(0).to_numpy(dtype=float), marker="o", label=f"Jaccard@{plot_k}")
    plt.plot(x, _safe_numeric(df["overlap"]).fillna(0).to_numpy(dtype=float), marker="o", label=f"Overlap@{plot_k}")
    plt.plot(x, _safe_numeric(df["spearman"]).fillna(0).to_numpy(dtype=float), marker="o", label=f"Spearman@{plot_k}")
    plt.xlabel(df["param_name"].iloc[0])
    plt.ylabel("Значение метрики")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def _save_contributors_plot(contributor_df: pd.DataFrame, out_path: Path, title: str) -> None:
    """Сохраняет столбчатую диаграмму частоты explain-признаков.

    Args:
        contributor_df: Таблица частот признаков.
        out_path: Путь к PNG-файлу.
        title: Заголовок графика.
    """
    if contributor_df.empty:
        return
    df: pd.DataFrame = contributor_df.head(10).copy()
    plt.figure()
    plt.bar(df["feature"].astype(str), _safe_numeric(df["count"]).fillna(0).to_numpy(dtype=float))
    plt.xticks(rotation=90)
    plt.xlabel("Признак")
    plt.ylabel("Частота появления")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def _save_json(path: Path, payload: dict[str, object]) -> None:
    """Сохраняет словарь в JSON-файл в кодировке UTF-8.

    Args:
        path: Путь к выходному JSON.
        payload: Словарь с сериализуемыми данными.
    """
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _scores_to_console_brief(
    entity_type: str,
    target_date: str,
    proxy_df: pd.DataFrame,
    stability_df: pd.DataFrame,
    contributor_df: pd.DataFrame,
    cfg: ExperimentConfig,
) -> None:
    """Печатает краткую консольную сводку по одному типу сущности.

    Args:
        entity_type: Тип сущности.
        target_date: Целевая дата.
        proxy_df: Сводная таблица прокси-метрик.
        stability_df: Таблица устойчивости.
        contributor_df: Таблица частот объясняющих признаков.
        cfg: Конфигурация запуска.
    """
    row = proxy_df.iloc[0].to_dict() if not proxy_df.empty else {}

    def _metric_values(param_group: str, metric: str) -> str:
        df = stability_df[
            (stability_df["param_group"].astype(str) == param_group) & (stability_df["k"].astype(int) == int(cfg.plot_k))
        ]
        if df.empty:
            return "нет данных"
        series = _safe_numeric(df[metric]).fillna(0)
        return " / ".join(f"{value:.2f}" for value in series.tolist())

    print()
    print(f"Дата: {target_date}")
    print(f"Сущность: {entity_type}")
    print(f"Строк в анализе: {int(row.get('rows_total', 0))}")
    print(f"Tail ratio p95/median: {float(row.get('tail_ratio_p95_median', 0.0)):.3f}")
    print(f"Critical anomalies: {int(row.get('critical_count', 0))}")
    print(f"High anomalies: {int(row.get('high_count', 0))}")
    print(f"Jaccard@{cfg.plot_k} by contamination: {_metric_values('contamination', 'jaccard')}")
    print(f"Overlap@{cfg.plot_k} by contamination: {_metric_values('contamination', 'overlap')}")
    print(f"Spearman@{cfg.plot_k} by contamination: {_metric_values('contamination', 'spearman')}")
    print(f"Jaccard@{cfg.plot_k} by n_neighbors: {_metric_values('n_neighbors', 'jaccard')}")
    print(f"Overlap@{cfg.plot_k} by n_neighbors: {_metric_values('n_neighbors', 'overlap')}")
    print(f"Spearman@{cfg.plot_k} by n_neighbors: {_metric_values('n_neighbors', 'spearman')}")
    if not contributor_df.empty:
        top_features: str = ", ".join(contributor_df.head(5)["feature"].astype(str).tolist())
        print(f"Most frequent contributors: {top_features}")
    else:
        print("Most frequent contributors: explain-файл отсутствует или не содержит данных")


def _run_one_kind(kind: str, features_df: pd.DataFrame, cfg: ExperimentConfig) -> dict[str, object]:
    """Выполняет полный расчёт прокси-метрик для одного типа сущности.

    Args:
        kind: Тип сущности: users или hosts.
        features_df: Полная таблица признаков.
        cfg: Конфигурация запуска.

    Returns:
        Словарь с путями к выходным артефактам и краткими итогами.
    """
    entity_type: str = kind
    base_scores: pd.DataFrame = _run_scores_for_day(
        features_df=features_df,
        target_date=cfg.target_date,
        contamination=cfg.contamination,
        n_estimators=cfg.n_estimators,
        n_neighbors=cfg.n_neighbors,
        random_state=cfg.random_state,
    )

    explain_df: pd.DataFrame | None = _read_explain_file(cfg.anomaly_dir, kind, cfg.target_date)
    contributor_df: pd.DataFrame = _aggregate_contributors(
        explain_df=explain_df,
        contributor_severities=cfg.contributor_severities,
        strict_explain=cfg.strict_explain,
        entity_type=entity_type,
        target_date=cfg.target_date,
    )

    stability_cont: pd.DataFrame = _stability_against_contamination(
        base_scores=base_scores,
        features_df=features_df,
        target_date=cfg.target_date,
        cfg=cfg,
        entity_type=entity_type,
    )
    stability_neigh: pd.DataFrame = _stability_against_neighbors(
        base_scores=base_scores,
        features_df=features_df,
        target_date=cfg.target_date,
        cfg=cfg,
        entity_type=entity_type,
    )
    stability_df: pd.DataFrame = pd.concat([stability_cont, stability_neigh], ignore_index=True)

    score_summary: dict[str, float | int] = _score_summary(base_scores)
    proxy_df: pd.DataFrame = _build_proxy_metrics_table(
        entity_type=entity_type,
        target_date=cfg.target_date,
        score_summary=score_summary,
        stability_df=stability_df,
        contributor_df=contributor_df,
        ks=cfg.ks,
    )

    if cfg.save_score_tables:
        base_scores.to_csv(cfg.out_dir / f"day_scores_{kind}_{cfg.target_date}.csv", index=False)

    proxy_path: Path = cfg.out_dir / f"proxy_metrics_{kind}_{cfg.target_date}.csv"
    stability_path: Path = cfg.out_dir / f"stability_{kind}_{cfg.target_date}.csv"
    contributors_path: Path = cfg.out_dir / f"contributors_{kind}_{cfg.target_date}.csv"

    proxy_df.to_csv(proxy_path, index=False)
    stability_df.to_csv(stability_path, index=False)
    contributor_df.to_csv(contributors_path, index=False)

    _save_score_histogram(
        scores=base_scores,
        out_path=cfg.out_dir / f"score_hist_{kind}_{cfg.target_date}.png",
        title=f"Распределение нормированной оценки аномальности для {kind} за {cfg.target_date}",
    )
    _save_stability_plot(
        stability_df=stability_df,
        out_path=cfg.out_dir / f"stability_contamination_{kind}_{cfg.target_date}.png",
        title=f"Устойчивость top-{cfg.plot_k} аномалий {kind} при варьировании contamination",
        param_group="contamination",
        plot_k=cfg.plot_k,
    )
    _save_stability_plot(
        stability_df=stability_df,
        out_path=cfg.out_dir / f"stability_neighbors_{kind}_{cfg.target_date}.png",
        title=f"Устойчивость top-{cfg.plot_k} аномалий {kind} при варьировании n_neighbors",
        param_group="n_neighbors",
        plot_k=cfg.plot_k,
    )
    _save_contributors_plot(
        contributor_df=contributor_df,
        out_path=cfg.out_dir / f"contributors_freq_{kind}_{cfg.target_date}.png",
        title=f"Частота признаков, определяющих аномальность {kind}",
    )

    _scores_to_console_brief(
        entity_type=entity_type,
        target_date=cfg.target_date,
        proxy_df=proxy_df,
        stability_df=stability_df,
        contributor_df=contributor_df,
        cfg=cfg,
    )

    return {
        "proxy_metrics_csv": str(proxy_path),
        "stability_csv": str(stability_path),
        "contributors_csv": str(contributors_path),
        "score_hist_png": str(cfg.out_dir / f"score_hist_{kind}_{cfg.target_date}.png"),
        "stability_contamination_png": str(cfg.out_dir / f"stability_contamination_{kind}_{cfg.target_date}.png"),
        "stability_neighbors_png": str(cfg.out_dir / f"stability_neighbors_{kind}_{cfg.target_date}.png"),
        "contributors_png": str(cfg.out_dir / f"contributors_freq_{kind}_{cfg.target_date}.png"),
        "rows_total": int(score_summary.get("rows_total", 0)),
    }


def _write_summary_json(cfg: ExperimentConfig, results: dict[str, dict[str, object]]) -> Path:
    """Сохраняет итоговое JSON-резюме запуска.

    Args:
        cfg: Конфигурация запуска.
        results: Словарь результатов по типам сущностей.

    Returns:
        Путь к сохранённому JSON-файлу.
    """
    payload: dict[str, object] = {
        "target_date": cfg.target_date,
        "parameters": {
            "contamination": cfg.contamination,
            "n_estimators": cfg.n_estimators,
            "n_neighbors": cfg.n_neighbors,
            "random_state": cfg.random_state,
            "ks": list(cfg.ks),
            "plot_k": cfg.plot_k,
            "contamination_grid": list(cfg.contamination_grid),
            "neighbors_grid": list(cfg.neighbors_grid),
            "contributor_severities": list(cfg.contributor_severities),
        },
        "paths": {
            "work_dir": str(cfg.work_dir),
            "anomaly_dir": str(cfg.anomaly_dir),
            "out_dir": str(cfg.out_dir),
        },
        "results": results,
    }
    out_path: Path = cfg.out_dir / f"proxy_metrics_summary_{cfg.target_date}.json"
    _save_json(out_path, payload)
    return out_path


def _parse_args() -> argparse.Namespace:
    """Описывает и разбирает аргументы командной строки.

    Returns:
        Namespace с параметрами запуска.
    """
    parser = argparse.ArgumentParser(
        description="Расчёт прокси-метрик качества безнадзорной модели обнаружения аномалий"
    )
    parser.add_argument("--work", default="features", help="Директория с features_*_clean.csv (по умолчанию: features)")
    parser.add_argument(
        "--anomaly-dir",
        default=None,
        help="Директория с anomalies_*_explain.csv (по умолчанию: совпадает с --work)",
    )
    parser.add_argument(
        "--out-dir",
        default="report/metrics",
        help="Директория для сохранения метрик и графиков (по умолчанию: report/metrics)",
    )
    parser.add_argument("--date", default=None, help="Целевая дата YYYY-MM-DD (по умолчанию: последняя в features)")
    parser.add_argument("--contamination", type=float, default=0.05, help="Базовое значение contamination")
    parser.add_argument("--n-estimators", type=int, default=300, help="Базовое число деревьев Isolation Forest")
    parser.add_argument("--n-neighbors", type=int, default=20, help="Базовое число соседей LOF")
    parser.add_argument("--random-state", type=int, default=42, help="Фиксация случайности")
    parser.add_argument(
        "--k-list",
        default="10,20",
        help="Список значений K для Jaccard@K / Overlap@K / Spearman@K, например '10,20'",
    )
    parser.add_argument("--plot-k", type=int, default=10, help="Какое значение K использовать на графиках устойчивости")
    parser.add_argument(
        "--contamination-grid",
        default="0.03,0.05,0.07",
        help="Набор значений contamination для анализа устойчивости",
    )
    parser.add_argument(
        "--neighbors-grid",
        default="15,20,25",
        help="Набор значений n_neighbors для анализа устойчивости",
    )
    parser.add_argument(
        "--contributor-severities",
        default="critical,high",
        help="Какие уровни severity включать в анализ explainability",
    )
    parser.add_argument(
        "--strict-explain",
        action="store_true",
        help="Считать отсутствие explain-файлов ошибкой",
    )
    parser.add_argument(
        "--save-score-tables",
        action="store_true",
        help="Сохранять полные дневные таблицы скоринга по пользователям и хостам",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа для расчёта прокси-метрик качества.

    Returns:
        Код завершения процесса.
    """
    args: argparse.Namespace = _parse_args()
    cfg: ExperimentConfig = _build_config(args)

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    _save_json(
        cfg.out_dir / f"proxy_metrics_requested_run_{cfg.target_date}.json",
        {
            "target_date": cfg.target_date,
            "work_dir": str(cfg.work_dir),
            "anomaly_dir": str(cfg.anomaly_dir),
            "out_dir": str(cfg.out_dir),
            "parameters": {
                "contamination": cfg.contamination,
                "n_estimators": cfg.n_estimators,
                "n_neighbors": cfg.n_neighbors,
                "random_state": cfg.random_state,
                "ks": list(cfg.ks),
                "plot_k": cfg.plot_k,
                "contamination_grid": list(cfg.contamination_grid),
                "neighbors_grid": list(cfg.neighbors_grid),
                "contributor_severities": list(cfg.contributor_severities),
                "strict_explain": cfg.strict_explain,
                "save_score_tables": cfg.save_score_tables,
            },
        },
    )

    users_df: pd.DataFrame = core.load_features(cfg.work_dir, "users")
    hosts_df: pd.DataFrame = core.load_features(cfg.work_dir, "hosts")

    results: dict[str, dict[str, object]] = {}
    results["users"] = _run_one_kind("users", users_df, cfg)
    results["hosts"] = _run_one_kind("hosts", hosts_df, cfg)

    summary_path: Path = _write_summary_json(cfg, results)
    print()
    print(f"[+] Сводный JSON сохранён: {summary_path}")
    print("[*] Расчёт прокси-метрик завершён.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
