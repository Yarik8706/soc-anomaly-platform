#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
full_cycle.py

Единая точка входа для полного цикла обработки данных, построения отчётов и
расчёта прокси-метрик качества модели обнаружения аномалий.

Назначение скрипта:
    1. Нормализовать исходные выгрузки SIEM/NGFW.
    2. Построить таблицы признаков пользователей и хостов.
    3. Выполнить препроцессинг признаков.
    4. Посчитать аномалии по выбранным датам.
    5. Сформировать explainability-слой для аномалий.
    6. Построить графики и SOC-отчёты.
    7. При необходимости автоматически запустить evaluate_proxy_metrics.py.
    8. Сохранить конфигурацию запуска и manifest в едином каталоге артефактов.

Особенности реализации:
    - Поддерживается CLI-режим и интерактивный режим.
    - Все ключевые параметры и результаты запуска фиксируются в JSON.
    - Для каждого запуска создаётся отдельный каталог артефактов.
    - Аномалии, отчёты, метрики и технические файлы раскладываются по
      отдельным подкаталогам одного запуска.
    - Скрипт не дублирует бизнес-логику downstream-модулей, а выступает
      координатором существующего пайплайна.

Примеры запуска:
    python full_cycle.py --scope day --date 2025-12-31
    python full_cycle.py --scope month --date 2025-12-31 --run-mode report+metrics
    python full_cycle.py --scope range --start-date 2025-12-01 --end-date 2025-12-31 --for-thesis
    python full_cycle.py --scope all --run-mode metrics --reuse-prepared-data
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

import viz_core as core


VALID_SCOPES: tuple[str, ...] = ("day", "week", "month", "range", "all")
VALID_RUN_MODES: tuple[str, ...] = ("report", "metrics", "report+metrics")


@dataclass(frozen=True)
class PipelinePaths:
    """Абсолютные пути, используемые оркестратором.

    Attributes:
        base_dir: Базовая директория проекта.
        data_dir: Каталог с исходными TSV/TXT-выгрузками.
        work_dir: Каталог с нормализованными суточными CSV.
        features_dir: Каталог с таблицами признаков.
        report_root_dir: Корневой каталог всех запусков.
        run_dir: Каталог текущего запуска.
        anomalies_dir: Каталог аномалий и explain-файлов текущего запуска.
        reports_dir: Каталог графиков и SOC-отчётов текущего запуска.
        metrics_dir: Каталог прокси-метрик текущего запуска.
        meta_dir: Каталог технических JSON-файлов текущего запуска.
    """

    base_dir: Path
    data_dir: Path
    work_dir: Path
    features_dir: Path
    report_root_dir: Path
    run_dir: Path
    anomalies_dir: Path
    reports_dir: Path
    metrics_dir: Path
    meta_dir: Path


@dataclass(frozen=True)
class ExperimentConfig:
    """Параметры одного запуска полного цикла.

    Attributes:
        run_mode: Режим запуска: report, metrics, report+metrics.
        scope: Масштаб отчёта: day, week, month, range, all.
        target_date: Целевая дата, к которой относится запуск.
        dates_for_anomalies: Список дат, по которым выполняются train/explain.
        top_anomalies: Число верхних аномалий, экспортируемых train-модулем.
        top_features: Число факторов explainability для одной аномалии.
        top_pct: Доля верхних объектов для визуализации дневного отчёта.
        contamination: Базовый параметр contamination для IF/LOF.
        n_estimators: Число деревьев Isolation Forest.
        max_samples: Параметр max_samples для Isolation Forest.
        n_neighbors: Число соседей LOF.
        random_state: Фиксация случайности.
        for_thesis: Флаг исследовательского режима для ВКР.
        reuse_prepared_data: Пропуск нормализации и построения признаков.
        metrics_script: Имя скрипта расчёта прокси-метрик.
        metrics_k_list: Значения K для Jaccard@K / Overlap@K / Spearman@K.
        metrics_plot_k: Значение K, используемое на графиках устойчивости.
        metrics_contamination_grid: Сетка contamination для анализа устойчивости.
        metrics_neighbors_grid: Сетка n_neighbors для анализа устойчивости.
        contributor_severities: Уровни severity для анализа explainability.
        strict_metrics: Требовать обязательного наличия metrics-скрипта.
        strict_explain: Считать отсутствие explain-файлов ошибкой на этапе метрик.
        save_score_tables: Сохранять полные таблицы скоринга в модуле метрик.
        dry_run: Не запускать внешние процессы, а только напечатать план.
        run_tag: Произвольный тег запуска.
    """

    run_mode: str
    scope: str
    target_date: str
    dates_for_anomalies: list[str]
    top_anomalies: int
    top_features: int
    top_pct: float
    contamination: float
    n_estimators: int
    max_samples: str
    n_neighbors: int
    random_state: int
    for_thesis: bool
    reuse_prepared_data: bool
    metrics_script: str
    metrics_k_list: str
    metrics_plot_k: int
    metrics_contamination_grid: str
    metrics_neighbors_grid: str
    contributor_severities: str
    strict_metrics: bool
    strict_explain: bool
    save_score_tables: bool
    dry_run: bool
    run_tag: str


@dataclass
class StepResult:
    """Результат выполнения одного шага оркестратора.

    Attributes:
        name: Логическое имя шага.
        command: Полная команда внешнего процесса.
        status: Статус шага: success, failed, skipped, dry-run.
        started_at: Время начала шага в формате ISO.
        finished_at: Время завершения шага в формате ISO.
        return_code: Код возврата внешнего процесса.
        note: Дополнительное пояснение по шагу.
    """

    name: str
    command: list[str]
    status: str
    started_at: str
    finished_at: str
    return_code: int
    note: str = ""


@dataclass
class RunManifest:
    """Сводная информация о текущем запуске full_cycle.py.

    Attributes:
        started_at: Время старта оркестратора.
        finished_at: Время завершения оркестратора.
        paths: Абсолютные пути текущего запуска.
        experiment: Параметры текущего эксперимента.
        steps: Список шагов и их статусов.
        warnings: Предупреждения, не приведшие к аварийному завершению.
    """

    started_at: str
    finished_at: str
    paths: dict[str, str]
    experiment: dict[str, object]
    steps: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _now_iso() -> str:
    """Возвращает текущее время в ISO-формате до секунд.

    Returns:
        Строка времени в формате ISO 8601.
    """
    return datetime.now().replace(microsecond=0).isoformat()


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    """Преобразует путь к абсолютному виду относительно базовой директории.

    Args:
        base_dir: Базовая директория проекта.
        raw_path: Путь из CLI или значение по умолчанию.

    Returns:
        Абсолютный путь.
    """
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _script_path(base_dir: Path, filename: str) -> Path:
    """Возвращает путь до дочернего скрипта внутри проекта.

    Args:
        base_dir: Базовая директория проекта.
        filename: Имя вызываемого скрипта.

    Returns:
        Абсолютный путь до скрипта.
    """
    return (base_dir / filename).resolve()


def _parse_date(value: str) -> str:
    """Проверяет и нормализует дату к формату YYYY-MM-DD.

    Args:
        value: Исходная строка даты.

    Returns:
        Нормализованная строка YYYY-MM-DD.

    Raises:
        ValueError: Если дата некорректна.
    """
    return str(datetime.strptime(value.strip(), "%Y-%m-%d").date())


def _parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки.

    Returns:
        Пространство имён argparse с параметрами запуска.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Единая точка входа пайплайна: подготовка данных, аномалии, explainability, "
            "графики, SOC-отчёты и прокси-метрики качества."
        )
    )

    parser.add_argument("--scope", choices=VALID_SCOPES, default=None,
                        help="Масштаб запуска: day, week, month, range, all")
    parser.add_argument("--date", default=None,
                        help="Целевая дата YYYY-MM-DD для режимов day/week/month")
    parser.add_argument("--start-date", default=None,
                        help="Начало диапазона YYYY-MM-DD для scope=range")
    parser.add_argument("--end-date", default=None,
                        help="Конец диапазона YYYY-MM-DD для scope=range")

    parser.add_argument("--run-mode", choices=VALID_RUN_MODES, default=None,
                        help="Режим запуска: report, metrics, report+metrics")
    parser.add_argument("--for-thesis", action="store_true",
                        help="Исследовательский режим ВКР: форсирует report+metrics, если режим явно не задан")

    parser.add_argument("--data-dir", default="data",
                        help="Каталог с исходными выгрузками (по умолчанию: data)")
    parser.add_argument("--work-dir", default="work",
                        help="Рабочий каталог нормализованных CSV (по умолчанию: work)")
    parser.add_argument("--features-dir", default="features",
                        help="Каталог таблиц признаков (по умолчанию: features)")
    parser.add_argument("--report-dir", default="report",
                        help="Корневой каталог запусков (по умолчанию: report)")
    parser.add_argument("--run-tag", default="",
                        help="Необязательный тег запуска для имени каталога")

    parser.add_argument("--reuse-prepared-data", action="store_true",
                        help="Не запускать python_script.py, build_features_v2.py и preprocess_features.py")

    parser.add_argument("--top-anomalies", type=int, default=30,
                        help="Число верхних аномалий для train_anomaly_models.py")
    parser.add_argument("--top-features", type=int, default=5,
                        help="Число explain-признаков для explain_anomalies.py")
    parser.add_argument("--top-pct", type=float, default=0.05,
                        help="Доля верхних объектов для дневной визуализации")
    parser.add_argument("--contamination", type=float, default=0.05,
                        help="Параметр contamination для IF/LOF")
    parser.add_argument("--n-estimators", type=int, default=300,
                        help="Число деревьев Isolation Forest")
    parser.add_argument("--max-samples", default="auto",
                        help="Параметр max_samples для Isolation Forest")
    parser.add_argument("--n-neighbors", type=int, default=20,
                        help="Число соседей LOF")
    parser.add_argument("--random-state", type=int, default=42,
                        help="Значение генератора случайных чисел")

    parser.add_argument("--metrics-script", default="evaluate_proxy_metrics.py",
                        help="Имя скрипта расчёта прокси-метрик")
    parser.add_argument("--metrics-k-list", default="10,20",
                        help="Список значений K для модуля метрик, например '10,20'")
    parser.add_argument("--metrics-plot-k", type=int, default=10,
                        help="Значение K для графиков устойчивости")
    parser.add_argument("--metrics-contamination-grid", default="0.03,0.05,0.07",
                        help="Сетка contamination для анализа устойчивости")
    parser.add_argument("--metrics-neighbors-grid", default="15,20,25",
                        help="Сетка n_neighbors для анализа устойчивости")
    parser.add_argument("--contributor-severities", default="critical,high",
                        help="Какие уровни severity включать в анализ explainability")
    parser.add_argument("--strict-metrics", action="store_true",
                        help="Считать отсутствие metrics-скрипта ошибкой")
    parser.add_argument("--strict-explain", action="store_true",
                        help="Передавать модулю метрик строгую проверку наличия explain-файлов")
    parser.add_argument("--save-score-tables", action="store_true",
                        help="Передавать модулю метрик флаг сохранения полных таблиц скоринга")

    parser.add_argument("--dry-run", action="store_true",
                        help="Не выполнять внешние команды, а только печатать план запуска")

    return parser.parse_args()


def _prompt_scope() -> str:
    """Интерактивно запрашивает масштаб запуска.

    Returns:
        Выбранное значение scope.
    """
    mapping = {
        "1": "day",
        "2": "week",
        "3": "month",
        "4": "range",
        "5": "all",
    }
    print("Выберите масштаб запуска:")
    print("  1) День")
    print("  2) Неделя")
    print("  3) Месяц")
    print("  4) Диапазон")
    print("  5) За всё время")
    while True:
        choice = input("Введите номер варианта: ").strip()
        if choice in mapping:
            return mapping[choice]
        print("Некорректный выбор. Повторите ввод.")


def _prompt_run_mode() -> str:
    """Интерактивно запрашивает режим запуска.

    Returns:
        Выбранный режим: report, metrics или report+metrics.
    """
    mapping = {
        "1": "report",
        "2": "metrics",
        "3": "report+metrics",
    }
    print("Выберите режим запуска:")
    print("  1) Только отчёты")
    print("  2) Только метрики")
    print("  3) Отчёты и метрики")
    while True:
        choice = input("Введите номер варианта: ").strip()
        if choice in mapping:
            return mapping[choice]
        print("Некорректный выбор. Повторите ввод.")


def _prompt_date(label: str) -> str:
    """Интерактивно запрашивает дату и валидирует формат.

    Args:
        label: Текст приглашения к вводу.

    Returns:
        Дата в формате YYYY-MM-DD.
    """
    while True:
        raw = input(f"{label} (YYYY-MM-DD): ").strip()
        try:
            return _parse_date(raw)
        except ValueError:
            print("Неверный формат даты. Используйте YYYY-MM-DD.")


def _resolve_scope(args: argparse.Namespace) -> str:
    """Определяет итоговый scope на основании CLI или интерактива.

    Args:
        args: Аргументы командной строки.

    Returns:
        Значение scope.
    """
    return args.scope if args.scope else _prompt_scope()


def _resolve_run_mode(args: argparse.Namespace) -> str:
    """Определяет итоговый режим запуска.

    Логика:
        - если режим явно указан в CLI, он используется как базовый;
        - если режим не указан, но включён --for-thesis, используется report+metrics;
        - если ничего не задано, режим запрашивается интерактивно.

    Args:
        args: Аргументы командной строки.

    Returns:
        Итоговый режим запуска.
    """
    if args.run_mode:
        return args.run_mode
    if args.for_thesis:
        return "report+metrics"
    return _prompt_run_mode()


def _resolve_requested_dates(args: argparse.Namespace, scope: str) -> tuple[str, str, str]:
    """Определяет запрошенные пользователем даты до загрузки доступных данных.

    Args:
        args: Аргументы командной строки.
        scope: Выбранный масштаб запуска.

    Returns:
        Кортеж из значений (target_date, range_start, range_end).
    """
    target_date = ""
    range_start = ""
    range_end = ""

    if scope in {"day", "week", "month"}:
        if args.date:
            target_date = _parse_date(args.date)
        elif not args.dry_run:
            prompt_map = {
                "day": "Введите дату для дневного отчёта",
                "week": "Введите конечную дату недельного окна",
                "month": "Введите конечную дату месячного окна",
            }
            target_date = _prompt_date(prompt_map[scope])
    elif scope == "range":
        if args.start_date:
            range_start = _parse_date(args.start_date)
        elif not args.dry_run:
            range_start = _prompt_date("Введите начало диапазона")
        if args.end_date:
            range_end = _parse_date(args.end_date)
        elif not args.dry_run:
            range_end = _prompt_date("Введите конец диапазона")

    return target_date, range_start, range_end


def _filter_dates(available: Iterable[str], start: str, end: str) -> list[str]:
    """Возвращает отсортированный список дат внутри диапазона.

    Args:
        available: Доступные даты.
        start: Начало диапазона YYYY-MM-DD.
        end: Конец диапазона YYYY-MM-DD.

    Returns:
        Даты, попадающие в указанный диапазон.
    """
    dates = sorted(available)
    return [date_value for date_value in dates if start <= date_value <= end]


def _window_dates(available: list[str], target: str, scope: str) -> list[str]:
    """Формирует окно дат для режимов day/week/month.

    Args:
        available: Доступные даты признаков.
        target: Конечная дата окна.
        scope: Один из режимов day/week/month.

    Returns:
        Список дат окна, отсортированный по возрастанию.
    """
    if scope == "day":
        return [target]
    window = 7 if scope == "week" else 30
    index = available.index(target)
    start_index = max(0, index - (window - 1))
    return available[start_index:index + 1]


def _load_available_dates(features_dir: Path) -> list[str]:
    """Загружает доступные даты из очищенных таблиц признаков.

    Args:
        features_dir: Каталог с features_users_clean.csv и features_hosts_clean.csv.

    Returns:
        Отсортированный список доступных дат.
    """
    users = core.load_features(features_dir, "users")
    hosts = core.load_features(features_dir, "hosts")
    return core.available_dates(users, hosts)


def _resolve_target_and_dates(
    scope: str,
    available: list[str],
    target_date: str,
    range_start: str,
    range_end: str,
) -> tuple[str, list[str]]:
    """Определяет целевую дату и набор дат для train/explain.

    Args:
        scope: Масштаб запуска.
        available: Список доступных дат признаков.
        target_date: Запрошенная пользователем целевая дата.
        range_start: Начало диапазона для scope=range.
        range_end: Конец диапазона для scope=range.

    Returns:
        Кортеж (target, dates_for_anomalies).

    Raises:
        ValueError: Если даты некорректны или отсутствуют в данных.
    """
    if not available:
        raise ValueError("Не найдено доступных дат в таблицах признаков.")

    if scope in {"day", "week", "month"}:
        target = target_date or available[-1]
        if target not in available:
            raise ValueError(f"Дата {target} отсутствует в доступных данных.")
        return target, _window_dates(available, target, scope)

    if scope == "range":
        if not range_start or not range_end:
            raise ValueError("Для режима range необходимо задать start-date и end-date.")
        if range_start > range_end:
            raise ValueError("Начальная дата диапазона не может быть больше конечной.")
        dates_for_anomalies = _filter_dates(available, range_start, range_end)
        if not dates_for_anomalies:
            raise ValueError("В указанном диапазоне нет доступных дат.")
        return dates_for_anomalies[-1], dates_for_anomalies

    return available[-1], available


def _build_run_id(scope: str, target_date: str, run_tag: str) -> str:
    """Формирует уникальный идентификатор текущего запуска.

    Args:
        scope: Масштаб запуска.
        target_date: Целевая дата запуска.
        run_tag: Дополнительный пользовательский тег.

    Returns:
        Строка идентификатора запуска.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_tag = run_tag.strip().replace(" ", "_") if run_tag else ""
    parts = [scope, target_date, timestamp]
    if safe_tag:
        parts.append(safe_tag)
    return "__".join(parts)


def _prepare_paths(
    base_dir: Path,
    data_dir: Path,
    work_dir: Path,
    features_dir: Path,
    report_root_dir: Path,
    run_id: str,
) -> PipelinePaths:
    """Создаёт каталог артефактов запуска и возвращает структуру путей.

    Args:
        base_dir: Базовая директория проекта.
        data_dir: Каталог исходных выгрузок.
        work_dir: Рабочий каталог нормализованных CSV.
        features_dir: Каталог таблиц признаков.
        report_root_dir: Корневой каталог отчётов.
        run_id: Идентификатор текущего запуска.

    Returns:
        Структура абсолютных путей PipelinePaths.
    """
    run_dir = (report_root_dir / run_id).resolve()
    anomalies_dir = (run_dir / "anomalies").resolve()
    reports_dir = (run_dir / "reports").resolve()
    metrics_dir = (run_dir / "metrics").resolve()
    meta_dir = (run_dir / "meta").resolve()

    for directory in (run_dir, anomalies_dir, reports_dir, metrics_dir, meta_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return PipelinePaths(
        base_dir=base_dir.resolve(),
        data_dir=data_dir.resolve(),
        work_dir=work_dir.resolve(),
        features_dir=features_dir.resolve(),
        report_root_dir=report_root_dir.resolve(),
        run_dir=run_dir,
        anomalies_dir=anomalies_dir,
        reports_dir=reports_dir,
        metrics_dir=metrics_dir,
        meta_dir=meta_dir,
    )


def _save_json(path: Path, payload: dict[str, object]) -> None:
    """Сохраняет словарь в JSON с UTF-8 и читаемым форматированием.

    Args:
        path: Путь до итогового JSON-файла.
        payload: Сохраняемый словарь.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def _run_command(name: str, cmd: list[str], dry_run: bool) -> StepResult:
    """Запускает внешний процесс и возвращает структурированный результат.

    Args:
        name: Логическое имя шага.
        cmd: Полная команда запуска.
        dry_run: Если True, команда не выполняется.

    Returns:
        Объект StepResult.

    Raises:
        subprocess.CalledProcessError: Если команда завершилась с ошибкой.
    """
    started_at = _now_iso()
    print(f"\n[RUN] {' '.join(cmd)}")

    if dry_run:
        finished_at = _now_iso()
        return StepResult(
            name=name,
            command=cmd,
            status="dry-run",
            started_at=started_at,
            finished_at=finished_at,
            return_code=0,
            note="Команда не выполнялась из-за флага --dry-run.",
        )

    completed = subprocess.run(cmd, check=True)
    finished_at = _now_iso()
    return StepResult(
        name=name,
        command=cmd,
        status="success",
        started_at=started_at,
        finished_at=finished_at,
        return_code=int(completed.returncode),
    )


def _reports_enabled(run_mode: str) -> bool:
    """Определяет, требуется ли строить графики и SOC-отчёты.

    Args:
        run_mode: Режим запуска.

    Returns:
        True, если этап отчётов включён.
    """
    return run_mode in {"report", "report+metrics"}


def _metrics_enabled(run_mode: str) -> bool:
    """Определяет, требуется ли запускать модуль прокси-метрик.

    Args:
        run_mode: Режим запуска.

    Returns:
        True, если этап метрик включён.
    """
    return run_mode in {"metrics", "report+metrics"}


def _run_prepare_stage(paths: PipelinePaths, cfg: ExperimentConfig, steps: list[StepResult]) -> None:
    """Запускает предварительную подготовку данных.

    Этап включает:
        - python_script.py
        - build_features_v2.py
        - preprocess_features.py

    Args:
        paths: Структура путей текущего запуска.
        cfg: Параметры эксперимента.
        steps: Накопитель результатов выполнения шагов.
    """
    if cfg.reuse_prepared_data:
        steps.append(
            StepResult(
                name="prepare_data",
                command=[],
                status="skipped",
                started_at=_now_iso(),
                finished_at=_now_iso(),
                return_code=0,
                note="Подготовка данных пропущена из-за флага --reuse-prepared-data.",
            )
        )
        return

    prepare_commands = [
        (
            "normalize_raw_exports",
            [
                sys.executable,
                str(_script_path(paths.base_dir, "python_script.py")),
                "--data", str(paths.data_dir),
                "--work", str(paths.work_dir),
            ],
        ),
        (
            "build_features",
            [
                sys.executable,
                str(_script_path(paths.base_dir, "build_features_v2.py")),
                "--work", str(paths.work_dir),
                "--features-dir", str(paths.features_dir),
            ],
        ),
        (
            "preprocess_features",
            [
                sys.executable,
                str(_script_path(paths.base_dir, "preprocess_features.py")),
                "--work", str(paths.features_dir),
            ],
        ),
    ]

    for name, command in prepare_commands:
        steps.append(_run_command(name, command, cfg.dry_run))


def _run_train_and_explain(
    paths: PipelinePaths,
    cfg: ExperimentConfig,
    steps: list[StepResult],
) -> None:
    """Запускает train и explain для всех требуемых дат.

    Args:
        paths: Пути текущего запуска.
        cfg: Параметры эксперимента.
        steps: Накопитель результатов выполнения шагов.
    """
    train_script = _script_path(paths.base_dir, "train_anomaly_models.py")
    explain_script = _script_path(paths.base_dir, "explain_anomalies.py")

    for day in cfg.dates_for_anomalies:
        train_cmd = [
            sys.executable,
            str(train_script),
            "--work", str(paths.features_dir),
            "--out-dir", str(paths.anomalies_dir),
            "--date", day,
            "--top", str(cfg.top_anomalies),
            "--contamination", str(cfg.contamination),
            "--n-estimators", str(cfg.n_estimators),
            "--max-samples", str(cfg.max_samples),
            "--n-neighbors", str(cfg.n_neighbors),
            "--random-state", str(cfg.random_state),
        ]
        explain_cmd = [
            sys.executable,
            str(explain_script),
            "--work", str(paths.features_dir),
            "--anomaly-dir", str(paths.anomalies_dir),
            "--date", day,
            "--top-features", str(cfg.top_features),
        ]

        steps.append(_run_command(f"train_anomalies_{day}", train_cmd, cfg.dry_run))
        steps.append(_run_command(f"explain_anomalies_{day}", explain_cmd, cfg.dry_run))


def _run_reporting(paths: PipelinePaths, cfg: ExperimentConfig, steps: list[StepResult]) -> None:
    """Запускает визуализацию и SOC-отчёты.

    Для режимов day/week/month строится один отчёт заданного масштаба.
    Для режимов range/all формируются отдельные дневные отчёты по каждой дате.

    Args:
        paths: Пути текущего запуска.
        cfg: Параметры эксперимента.
        steps: Накопитель результатов выполнения шагов.
    """
    visualize_script = _script_path(paths.base_dir, "visualize_reports.py")
    soc_script = _script_path(paths.base_dir, "soc_report.py")

    if cfg.scope in {"day", "week", "month"}:
        visualize_cmd = [
            sys.executable,
            str(visualize_script),
            "--work", str(paths.features_dir),
            "--report-dir", str(paths.reports_dir),
            "--scope", cfg.scope,
            "--date", cfg.target_date,
            "--top-pct", str(cfg.top_pct),
            "--contamination", str(cfg.contamination),
            "--n-estimators", str(cfg.n_estimators),
            "--n-neighbors", str(cfg.n_neighbors),
            "--random-state", str(cfg.random_state),
        ]
        soc_cmd = [
            sys.executable,
            str(soc_script),
            "--work", str(paths.work_dir),
            "--features-dir", str(paths.features_dir),
            "--anomaly-dir", str(paths.anomalies_dir),
            "--report-dir", str(paths.reports_dir),
            "--scope", cfg.scope,
            "--date", cfg.target_date,
        ]
        steps.append(_run_command(f"visualize_{cfg.scope}_{cfg.target_date}", visualize_cmd, cfg.dry_run))
        steps.append(_run_command(f"soc_report_{cfg.scope}_{cfg.target_date}", soc_cmd, cfg.dry_run))
        return

    for day in cfg.dates_for_anomalies:
        visualize_cmd = [
            sys.executable,
            str(visualize_script),
            "--work", str(paths.features_dir),
            "--report-dir", str(paths.reports_dir),
            "--scope", "day",
            "--date", day,
            "--top-pct", str(cfg.top_pct),
            "--contamination", str(cfg.contamination),
            "--n-estimators", str(cfg.n_estimators),
            "--n-neighbors", str(cfg.n_neighbors),
            "--random-state", str(cfg.random_state),
        ]
        soc_cmd = [
            sys.executable,
            str(soc_script),
            "--work", str(paths.work_dir),
            "--features-dir", str(paths.features_dir),
            "--anomaly-dir", str(paths.anomalies_dir),
            "--report-dir", str(paths.reports_dir),
            "--scope", "day",
            "--date", day,
        ]
        steps.append(_run_command(f"visualize_day_{day}", visualize_cmd, cfg.dry_run))
        steps.append(_run_command(f"soc_report_day_{day}", soc_cmd, cfg.dry_run))


def _run_proxy_metrics(
    paths: PipelinePaths,
    cfg: ExperimentConfig,
    steps: list[StepResult],
    warnings: list[str],
) -> None:
    """Запускает evaluate_proxy_metrics.py по всем нужным датам.

    Args:
        paths: Пути текущего запуска.
        cfg: Параметры эксперимента.
        steps: Накопитель результатов выполнения шагов.
        warnings: Список предупреждений запуска.

    Raises:
        FileNotFoundError: Если metrics-скрипт обязателен, но отсутствует.
    """
    metrics_script_path = _script_path(paths.base_dir, cfg.metrics_script)
    if not metrics_script_path.exists():
        message = f"Скрипт метрик не найден: {metrics_script_path}"
        if cfg.strict_metrics:
            raise FileNotFoundError(message)
        warnings.append(message)
        steps.append(
            StepResult(
                name="proxy_metrics",
                command=[],
                status="skipped",
                started_at=_now_iso(),
                finished_at=_now_iso(),
                return_code=0,
                note=message,
            )
        )
        return

    for day in cfg.dates_for_anomalies:
        cmd = [
            sys.executable,
            str(metrics_script_path),
            "--work", str(paths.features_dir),
            "--anomaly-dir", str(paths.anomalies_dir),
            "--out-dir", str(paths.metrics_dir),
            "--date", day,
            "--contamination", str(cfg.contamination),
            "--n-estimators", str(cfg.n_estimators),
            "--n-neighbors", str(cfg.n_neighbors),
            "--random-state", str(cfg.random_state),
            "--k-list", str(cfg.metrics_k_list),
            "--plot-k", str(cfg.metrics_plot_k),
            "--contamination-grid", str(cfg.metrics_contamination_grid),
            "--neighbors-grid", str(cfg.metrics_neighbors_grid),
            "--contributor-severities", str(cfg.contributor_severities),
        ]
        if cfg.strict_explain:
            cmd.append("--strict-explain")
        if cfg.save_score_tables or cfg.for_thesis:
            cmd.append("--save-score-tables")

        steps.append(_run_command(f"proxy_metrics_{day}", cmd, cfg.dry_run))


def _build_manifest(
    started_at: str,
    finished_at: str,
    paths: PipelinePaths,
    cfg: ExperimentConfig,
    steps: list[StepResult],
    warnings: list[str],
) -> RunManifest:
    """Формирует итоговый manifest текущего запуска.

    Args:
        started_at: Время старта orchestrator.
        finished_at: Время завершения orchestrator.
        paths: Пути текущего запуска.
        cfg: Параметры эксперимента.
        steps: Выполненные шаги.
        warnings: Накопленные предупреждения.

    Returns:
        Объект manifest.
    """
    return RunManifest(
        started_at=started_at,
        finished_at=finished_at,
        paths={key: str(value) for key, value in asdict(paths).items()},
        experiment=asdict(cfg),
        steps=[asdict(step) for step in steps],
        warnings=warnings,
    )


def main() -> int:
    """Точка входа оркестратора полного цикла.

    Returns:
        Код завершения процесса.
    """
    started_at = _now_iso()
    args = _parse_args()

    base_dir = Path(__file__).resolve().parent
    scope = _resolve_scope(args)
    run_mode = _resolve_run_mode(args)

    warnings: list[str] = []
    if args.for_thesis and run_mode == "report":
        warnings.append(
            "Флаг --for-thesis использован вместе с run-mode=report. "
            "Режим автоматически повышен до report+metrics."
        )
        run_mode = "report+metrics"

    target_date_requested, range_start, range_end = _resolve_requested_dates(args, scope)

    data_dir = _resolve_path(base_dir, args.data_dir)
    work_dir = _resolve_path(base_dir, args.work_dir)
    features_dir = _resolve_path(base_dir, args.features_dir)
    report_root_dir = _resolve_path(base_dir, args.report_dir)
    report_root_dir.mkdir(parents=True, exist_ok=True)

    steps: list[StepResult] = []

    temp_paths = PipelinePaths(
        base_dir=base_dir,
        data_dir=data_dir,
        work_dir=work_dir,
        features_dir=features_dir,
        report_root_dir=report_root_dir,
        run_dir=report_root_dir,
        anomalies_dir=report_root_dir,
        reports_dir=report_root_dir,
        metrics_dir=report_root_dir,
        meta_dir=report_root_dir,
    )

    _run_prepare_stage(temp_paths, ExperimentConfig(
        run_mode=run_mode,
        scope=scope,
        target_date="",
        dates_for_anomalies=[],
        top_anomalies=int(args.top_anomalies),
        top_features=int(args.top_features),
        top_pct=float(args.top_pct),
        contamination=float(args.contamination),
        n_estimators=int(args.n_estimators),
        max_samples=str(args.max_samples),
        n_neighbors=int(args.n_neighbors),
        random_state=int(args.random_state),
        for_thesis=bool(args.for_thesis),
        reuse_prepared_data=bool(args.reuse_prepared_data),
        metrics_script=str(args.metrics_script),
        metrics_k_list=str(args.metrics_k_list),
        metrics_plot_k=int(args.metrics_plot_k),
        metrics_contamination_grid=str(args.metrics_contamination_grid),
        metrics_neighbors_grid=str(args.metrics_neighbors_grid),
        contributor_severities=str(args.contributor_severities),
        strict_metrics=bool(args.strict_metrics),
        strict_explain=bool(args.strict_explain),
        save_score_tables=bool(args.save_score_tables),
        dry_run=bool(args.dry_run),
        run_tag=str(args.run_tag or ""),
    ), steps)

    available_dates = _load_available_dates(features_dir)
    target_date, dates_for_anomalies = _resolve_target_and_dates(
        scope=scope,
        available=available_dates,
        target_date=target_date_requested,
        range_start=range_start,
        range_end=range_end,
    )

    run_id = _build_run_id(scope, target_date, str(args.run_tag or ""))
    paths = _prepare_paths(
        base_dir=base_dir,
        data_dir=data_dir,
        work_dir=work_dir,
        features_dir=features_dir,
        report_root_dir=report_root_dir,
        run_id=run_id,
    )

    cfg = ExperimentConfig(
        run_mode=run_mode,
        scope=scope,
        target_date=target_date,
        dates_for_anomalies=dates_for_anomalies,
        top_anomalies=int(args.top_anomalies),
        top_features=int(args.top_features),
        top_pct=float(args.top_pct),
        contamination=float(args.contamination),
        n_estimators=int(args.n_estimators),
        max_samples=str(args.max_samples),
        n_neighbors=int(args.n_neighbors),
        random_state=int(args.random_state),
        for_thesis=bool(args.for_thesis),
        reuse_prepared_data=bool(args.reuse_prepared_data),
        metrics_script=str(args.metrics_script),
        metrics_k_list=str(args.metrics_k_list),
        metrics_plot_k=int(args.metrics_plot_k),
        metrics_contamination_grid=str(args.metrics_contamination_grid),
        metrics_neighbors_grid=str(args.metrics_neighbors_grid),
        contributor_severities=str(args.contributor_severities),
        strict_metrics=bool(args.strict_metrics),
        strict_explain=bool(args.strict_explain),
        save_score_tables=bool(args.save_score_tables),
        dry_run=bool(args.dry_run),
        run_tag=str(args.run_tag or ""),
    )

    _save_json(paths.meta_dir / "requested_run.json", {
        "raw_args": vars(args),
        "resolved_scope": scope,
        "resolved_run_mode": run_mode,
        "resolved_target_date": target_date,
        "dates_for_anomalies": dates_for_anomalies,
        "available_dates": available_dates,
    })
    _save_json(paths.meta_dir / "run_config.json", asdict(cfg))

    _run_train_and_explain(paths, cfg, steps)

    if _reports_enabled(cfg.run_mode):
        _run_reporting(paths, cfg, steps)

    if _metrics_enabled(cfg.run_mode):
        _run_proxy_metrics(paths, cfg, steps, warnings)

    finished_at = _now_iso()
    manifest = _build_manifest(
        started_at=started_at,
        finished_at=finished_at,
        paths=paths,
        cfg=cfg,
        steps=steps,
        warnings=warnings,
    )
    _save_json(paths.meta_dir / "manifest.json", asdict(manifest))

    print("\nГотово: полный цикл выполнен успешно.")
    print(f"Каталог запуска: {paths.run_dir}")
    print(f"Аномалии: {paths.anomalies_dir}")
    print(f"Отчёты: {paths.reports_dir}")
    print(f"Метрики: {paths.metrics_dir}")
    print(f"Meta: {paths.meta_dir}")
    if warnings:
        print("\nПредупреждения:")
        for message in warnings:
            print(f" - {message}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
