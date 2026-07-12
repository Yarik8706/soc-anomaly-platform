#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
full_cycle.py

Единая точка входа для полного цикла подготовки данных, поиска аномалий,
построения отчётов и подключения прокси-метрик качества.

Скрипт предназначен для оркестрации уже существующих модулей проекта и решает
следующие задачи:
  1) нормализация исходных выгрузок SIEM и NGFW;
  2) построение суточных признаков пользователей и хостов;
  3) очистка и подготовка таблиц признаков;
  4) запуск скоринга аномалий по выбранным датам;
  5) запуск explainability-слоя;
  6) формирование графиков и SOC-отчётов;
  7) подготовка конфигурации эксперимента и manifest-файла;
  8) интеграция с будущим модулем расчёта прокси-метрик качества.

Особенности версии:
  - поддерживается как CLI-режим, так и интерактивный ввод;
  - все пути, параметры и результаты запуска фиксируются в JSON;
  - режимы запуска разделены на эксплуатационный и исследовательский;
  - предусмотрена мягкая интеграция со скриптом evaluate_proxy_metrics.py,
    который может быть добавлен позднее без переделки оркестратора.

Примеры запуска:
  python full_cycle.py --scope day --date 2025-12-31
  python full_cycle.py --scope month --date 2025-12-31 --run-mode report+metrics --for-thesis
  python full_cycle.py --scope range --start-date 2025-12-01 --end-date 2025-12-31 --reuse-prepared-data
  python full_cycle.py --scope all --run-mode report --dry-run
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


@dataclass(frozen=True)
class ПутиКонвейера:
    """Структура абсолютных путей, используемых в конвейере.

    Атрибуты:
        base_dir: базовая директория проекта, где расположен orchestrator
        data_dir: директория с исходными TSV/TXT-выгрузками
        work_dir: рабочая директория с нормализованными дневными CSV
        features_dir: директория с построенными таблицами признаков
        report_root_dir: корневая директория хранения всех запусков
        run_dir: директория конкретного запуска
        report_output_dir: директория, в которую downstream-скрипты сохраняют
            графики и markdown-отчёты
        meta_dir: директория для конфигурации, manifest и технических файлов
        metrics_dir: директория для будущих метрик качества
    """

    base_dir: Path
    data_dir: Path
    work_dir: Path
    features_dir: Path
    report_root_dir: Path
    run_dir: Path
    report_output_dir: Path
    meta_dir: Path
    metrics_dir: Path


@dataclass(frozen=True)
class ПараметрыЭксперимента:
    """Набор параметров, управляющих расчётом аномалий и отчётностью.

    Атрибуты:
        run_mode: режим запуска orchestrator
        scope: масштаб отчёта: day/week/month/range/all
        target_date: целевая дата запуска. Для week/month это конечная дата окна,
            для range/all — последняя дата обрабатываемого диапазона
        dates_for_anomalies: список дат, по которым будет выполнен train/explain
        top_anomalies: число верхних аномалий, сохраняемых train-модулем
        top_features: число признаков в explainability-слое
        top_pct: доля верхних объектов для визуализации дневного отчёта
        contamination: оценка доли аномалий для IF/LOF
        n_estimators: число деревьев Isolation Forest
        max_samples: параметр max_samples для Isolation Forest
        n_neighbors: число соседей для LOF
        random_state: значение генератора случайных чисел
        for_thesis: флаг исследовательского режима для ВКР
        reuse_prepared_data: пропуск предварительных шагов подготовки данных
        metrics_script: имя скрипта, рассчитывающего прокси-метрики качества
        strict_metrics: требовать наличия metrics-скрипта в исследовательском режиме
        dry_run: не выполнять внешние команды, а только печатать план запуска
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
    strict_metrics: bool
    dry_run: bool


@dataclass
class РезультатШага:
    """Результат выполнения одного внешнего шага конвейера.

    Атрибуты:
        name: логическое имя шага
        command: полная команда запуска внешнего процесса
        status: итоговый статус шага
        started_at: время начала шага в ISO-формате
        finished_at: время завершения шага в ISO-формате
        return_code: код возврата процесса
        note: дополнительный комментарий по результату шага
    """

    name: str
    command: list[str]
    status: str
    started_at: str
    finished_at: str
    return_code: int
    note: str = ""


@dataclass
class МанифестЗапуска:
    """Сводная информация о выполнении orchestrator.

    Атрибуты:
        started_at: время старта orchestrator
        finished_at: время завершения orchestrator
        paths: использованные абсолютные пути проекта
        experiment: параметры текущего запуска
        steps: список выполненных шагов и их статусы
        warnings: список предупреждений, не приводящих к аварийному завершению
    """

    started_at: str
    finished_at: str
    paths: dict[str, str]
    experiment: dict[str, object]
    steps: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


ДОПУСТИМЫЕ_SCOPE: tuple[str, ...] = ("day", "week", "month", "range", "all")
ДОПУСТИМЫЕ_РЕЖИМЫ: tuple[str, ...] = ("report", "metrics", "report+metrics")


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    """Преобразует пользовательский путь в абсолютный Path.

    Аргументы:
        base_dir: базовая директория проекта
        raw_path: путь из CLI или значения по умолчанию

    Возвращает абсолютный путь
    """
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _script_path(base_dir: Path, filename: str) -> Path:
    """Возвращает абсолютный путь до скрипта внутри проекта.

    Аргументы:
        base_dir: базовая директория проекта
        filename: имя файла скрипта

    Возвращает абсолютный путь до файла.
    """
    return (base_dir / filename).resolve()


def _parse_date(value: str) -> str:
    """Проверяет и нормализует дату в формате YYYY-MM-DD.

    Аргументы value: строковое представление даты

    Возвращает дату в нормализованном строковом виде YYYY-MM-DD
    Исключения:
        ValueError: если формат даты некорректен
    """
    parsed = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    return str(parsed)


def _parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки.

    Возвращает пространство имён argparse с параметрами запуска
    """
    parser = argparse.ArgumentParser(
        description=(
            "Единый orchestrator пайплайна: подготовка данных, обучение, explainability, "
            "графики, SOC-отчёты и подключение прокси-метрик качества."
        )
    )

    parser.add_argument("--scope", choices=ДОПУСТИМЫЕ_SCOPE, default=None,
                        help="Масштаб запуска: day, week, month, range, all")
    parser.add_argument("--date", default=None,
                        help="Целевая дата YYYY-MM-DD. Для week/month — конечная дата окна.")
    parser.add_argument("--start-date", default=None,
                        help="Начальная дата диапазона для scope=range")
    parser.add_argument("--end-date", default=None,
                        help="Конечная дата диапазона для scope=range")

    parser.add_argument("--run-mode", choices=ДОПУСТИМЫЕ_РЕЖИМЫ, default=None,
                        help="Режим запуска: report, metrics, report+metrics")
    parser.add_argument("--for-thesis", action="store_true",
                        help="Исследовательский режим для ВКР: фиксируем конфигурацию и включаем метрики")

    parser.add_argument("--data-dir", default="data",
                        help="Каталог с исходными выгрузками (по умолчанию: data)")
    parser.add_argument("--work-dir", default="work",
                        help="Рабочий каталог нормализованных дневных CSV (по умолчанию: work)")
    parser.add_argument("--features-dir", default="features",
                        help="Каталог таблиц признаков (по умолчанию: features)")
    parser.add_argument("--report-dir", default="report",
                        help="Корневой каталог запускаемых отчётов (по умолчанию: report)")
    parser.add_argument("--run-tag", default=None,
                        help="Произвольный тег запуска для имени директории")

    parser.add_argument("--reuse-prepared-data", action="store_true",
                        help="Пропустить нормализацию, feature engineering и preprocess")
    parser.add_argument("--dry-run", action="store_true",
                        help="Не выполнять подпроцессы, а только вывести план запуска")

    parser.add_argument("--top-anomalies", type=int, default=30,
                        help="Число верхних аномалий, сохраняемых train-скриптом")
    parser.add_argument("--top-features", type=int, default=5,
                        help="Число признаков в explainability-слое")
    parser.add_argument("--top-pct", type=float, default=0.05,
                        help="Доля верхних объектов в визуализации дневного отчёта")
    parser.add_argument("--contamination", type=float, default=0.05,
                        help="Оценка доли аномалий для IF/LOF")
    parser.add_argument("--n-estimators", type=int, default=300,
                        help="Число деревьев Isolation Forest")
    parser.add_argument("--max-samples", default="auto",
                        help="Параметр max_samples для Isolation Forest")
    parser.add_argument("--n-neighbors", type=int, default=20,
                        help="Число соседей для LOF")
    parser.add_argument("--random-state", type=int, default=42,
                        help="Начальное значение генератора случайных чисел")

    parser.add_argument("--metrics-script", default="evaluate_proxy_metrics.py",
                        help="Имя скрипта расчёта прокси-метрик качества")
    parser.add_argument("--strict-metrics", action="store_true",
                        help="Завершать запуск с ошибкой, если metrics-скрипт отсутствует")

    return parser.parse_args()


def _prompt_choice(title: str, options: dict[str, str]) -> str:
    """Запрашивает выбор пользователя из нумерованного меню.

    Аргументы:
        title: заголовок меню
        options: словарь вариантов вида {"1": "value"}

    Возвращает значение выбранного варианта.
    """
    print(title)
    for number, value in options.items():
        print(f"  {number}) {value}")

    while True:
        choice = input("Введите номер варианта: ").strip()
        if choice in options:
            return options[choice]
        print("Некорректный выбор. Повторите ввод.")


def _prompt_scope() -> str:
    """Запрашивает масштаб отчёта в интерактивном режиме."""
    options = {
        "1": "day",
        "2": "week",
        "3": "month",
        "4": "range",
        "5": "all",
    }
    return _prompt_choice("Выберите масштаб запуска:", options)


def _prompt_run_mode() -> str:
    """Запрашивает режим работы orchestrator в интерактивном режиме."""
    options = {
        "1": "report",
        "2": "metrics",
        "3": "report+metrics",
    }
    return _prompt_choice("Выберите режим запуска:", options)


def _prompt_date(label: str) -> str:
    """Запрашивает дату у пользователя и валидирует формат.

    Аргументы label: подсказка для пользователя

    Возвращает нормализованную дату YYYY-MM-DD
    """
    while True:
        raw = input(f"{label} (YYYY-MM-DD): ").strip()
        try:
            return _parse_date(raw)
        except ValueError:
            print("Неверный формат. Используйте YYYY-MM-DD.")


def _resolve_runtime_choices(args: argparse.Namespace) -> tuple[str, str, str, str]:
    """Определяет режим запуска и даты с учётом CLI и интерактивного ввода.

    Аргумент args: объект argparse.Namespace

    Возвращает кортеж из значений (scope, run_mode, date, start_date, end_date)
    """
    scope = args.scope or _prompt_scope()
    run_mode = args.run_mode or _prompt_run_mode()

    target_date = args.date or ""
    start_date = args.start_date or ""
    end_date = args.end_date or ""

    if scope == "day" and not target_date:
        target_date = _prompt_date("Введите дату для дневного отчёта")
    elif scope == "week" and not target_date:
        target_date = _prompt_date("Введите конечную дату недельного окна")
    elif scope == "month" and not target_date:
        target_date = _prompt_date("Введите конечную дату месячного окна")
    elif scope == "range":
        if not start_date:
            start_date = _prompt_date("Введите начало диапазона")
        if not end_date:
            end_date = _prompt_date("Введите конец диапазона")

    return scope, run_mode, target_date, start_date, end_date


def _filter_dates(available_dates: Iterable[str], start_date: str, end_date: str) -> list[str]:
    """Фильтрует список дат по включённому диапазону.

    Аргументы:
        available_dates: Доступные даты из признакового пространства
        start_date: Начало диапазона
        end_date: Конец диапазона

    Возвращает отсортированный список дат, входящих в диапазон
    """
    ordered_dates = sorted(available_dates)
    return [item for item in ordered_dates if start_date <= item <= end_date]


def _window_dates(available_dates: list[str], target_date: str, scope: str) -> list[str]:
    """Формирует окно дат для режимов day/week/month.

    Аргументы:
        available_dates: все доступные даты в признаковых таблицах
        target_date: конечная дата окна
        scope: масштаб окна

    Возвращает список дат, по которым надо выполнить train/explain
    """
    if scope == "day":
        return [target_date]

    window_size = 7 if scope == "week" else 30
    target_index = available_dates.index(target_date)
    start_index = max(0, target_index - (window_size - 1))
    return available_dates[start_index: target_index + 1]


def _validate_cli_values(args: argparse.Namespace) -> None:
    """Проверяет числовые значения CLI-параметров.

    Аргумент args: объект argparse.Namespace

    Исключения:
        ValueError: Если один из параметров выходит за допустимые границы
    """
    if not (0.0 < args.contamination <= 0.5):
        raise ValueError("Параметр --contamination должен находиться в диапазоне (0, 0.5].")
    if args.top_anomalies <= 0:
        raise ValueError("Параметр --top-anomalies должен быть положительным.")
    if args.top_features <= 0:
        raise ValueError("Параметр --top-features должен быть положительным.")
    if not (0.0 < args.top_pct <= 1.0):
        raise ValueError("Параметр --top-pct должен находиться в диапазоне (0, 1].")
    if args.n_estimators <= 0:
        raise ValueError("Параметр --n-estimators должен быть положительным.")
    if args.n_neighbors <= 0:
        raise ValueError("Параметр --n-neighbors должен быть положительным.")


def _prepare_output_layout(
    report_root_dir: Path,
    scope: str,
    target_date: str,
    run_mode: str,
    run_tag: Optional[str],
) -> tuple[Path, Path, Path]:
    """Создаёт структуру директорий для одного запуска orchestrator.

    Аргументы:
        report_root_dir: корневая директория отчётов
        scope: масштаб запуска
        target_date: целевая дата запуска
        run_mode: режим запуска
        run_tag: пользовательский тег, если задан

    Возвращает кортеж (run_dir, report_output_dir, meta_dir, metrics_dir)
    """
    timestamp_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    normalized_mode = run_mode.replace("+", "_")
    suffix = run_tag.strip() if run_tag else timestamp_label
    run_dir = report_root_dir / f"run_{suffix}_{scope}_{target_date}_{normalized_mode}"
    report_output_dir = run_dir / "reports"
    meta_dir = run_dir / "meta"
    metrics_dir = run_dir / "metrics"

    for directory in (run_dir, report_output_dir, meta_dir, metrics_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return run_dir, report_output_dir, meta_dir, metrics_dir


def _build_paths(
    base_dir: Path,
    args: argparse.Namespace,
    scope: str,
    target_date: str,
    run_mode: str,
) -> ПутиКонвейера:
    """Строит полную карту путей текущего запуска.

    Аргументы:
        base_dir: базовая директория проекта
        args: аргументы командной строки
        scope: масштаб запуска
        target_date: целевая дата запуска
        run_mode: режим запуска

    Возвращает экземпляр "ПутиКонвейера" с абсолютными путями.
    """
    data_dir = _resolve_path(base_dir, args.data_dir)
    work_dir = _resolve_path(base_dir, args.work_dir)
    features_dir = _resolve_path(base_dir, args.features_dir)
    report_root_dir = _resolve_path(base_dir, args.report_dir)

    run_dir, report_output_dir, meta_dir, metrics_dir = _prepare_output_layout(
        report_root_dir=report_root_dir,
        scope=scope,
        target_date=target_date,
        run_mode=run_mode,
        run_tag=args.run_tag,
    )

    return ПутиКонвейера(
        base_dir=base_dir,
        data_dir=data_dir,
        work_dir=work_dir,
        features_dir=features_dir,
        report_root_dir=report_root_dir,
        run_dir=run_dir,
        report_output_dir=report_output_dir,
        meta_dir=meta_dir,
        metrics_dir=metrics_dir,
    )


def _run_command(name: str, command: list[str], dry_run: bool) -> РезультатШага:
    """Выполняет внешний шаг конвейера и возвращает его статус.

    Аргументы:
        name: логическое имя шага
        command: полная команда запуска
        dry_run: флаг режима без фактического выполнения

    Возвращает экземпляр "РезультатШага"

    Исключения:
        subprocess.CalledProcessError: Если подпроцесс завершился с ошибкой.
    """
    started_at = datetime.now().isoformat(timespec="seconds")
    print(f"\n[STEP] {name}")
    print(f"[CMD]  {' '.join(command)}")

    if dry_run:
        finished_at = datetime.now().isoformat(timespec="seconds")
        return РезультатШага(
            name=name,
            command=command,
            status="dry-run",
            started_at=started_at,
            finished_at=finished_at,
            return_code=0,
            note="Команда не выполнялась, потому что включён режим --dry-run.",
        )

    completed = subprocess.run(command, check=True)
    finished_at = datetime.now().isoformat(timespec="seconds")
    return РезультатШага(
        name=name,
        command=command,
        status="ok",
        started_at=started_at,
        finished_at=finished_at,
        return_code=int(completed.returncode),
    )


def _load_available_dates(features_dir: Path) -> list[str]:
    """Загружает подготовленные признаки и возвращает список доступных дат.

    Аргумент features_dir: директория с очищенными таблицами признаков

    Возвращает отсортированный список доступных дат
    """
    users = core.load_features(features_dir, "users")
    hosts = core.load_features(features_dir, "hosts")
    available_dates = core.available_dates(users, hosts)
    if not available_dates:
        raise ValueError("Не найдено доступных дат в таблицах признаков.")
    return available_dates


def _resolve_dates_for_scope(
    scope: str,
    target_date: str,
    start_date: str,
    end_date: str,
    available_dates: list[str],
) -> tuple[str, list[str]]:
    """Определяет целевую дату и набор дат для расчёта аномалий.

    Аргументы:
        scope: масштаб запуска
        target_date: целевая дата для day/week/month
        start_date: начальная дата диапазона для scope=range
        end_date: конечная дата диапазона для scope=range
        available_dates: доступные даты после preprocess

    Возвращает кортеж (resolved_target_date, dates_for_anomalies)
    """
    if scope in {"day", "week", "month"}:
        resolved_target = target_date or available_dates[-1]
        resolved_target = _parse_date(resolved_target)
        if resolved_target not in available_dates:
            raise ValueError(f"Дата {resolved_target} отсутствует в доступных данных.")
        return resolved_target, _window_dates(available_dates, resolved_target, scope)

    if scope == "range":
        if not start_date or not end_date:
            raise ValueError("Для scope=range необходимо указать --start-date и --end-date.")
        normalized_start = _parse_date(start_date)
        normalized_end = _parse_date(end_date)
        if normalized_start > normalized_end:
            raise ValueError("Начальная дата диапазона не может быть больше конечной.")
        selected_dates = _filter_dates(available_dates, normalized_start, normalized_end)
        if not selected_dates:
            raise ValueError("Внутри указанного диапазона нет доступных дат.")
        return selected_dates[-1], selected_dates

    if scope == "all":
        return available_dates[-1], available_dates

    raise ValueError(f"Неподдерживаемый scope: {scope}")


def _build_experiment_parameters(
    args: argparse.Namespace,
    scope: str,
    run_mode: str,
    target_date: str,
    dates_for_anomalies: list[str],
) -> ПараметрыЭксперимента:
    """Формирует объект параметров эксперимента.

    Аргументы:
        args: аргументы командной строки
        scope: масштаб запуска
        run_mode: режим запуска
        target_date: итоговая целевая дата
        dates_for_anomalies: набор дат для train/explain

    Возвращает экземпляр "ПараметрыЭксперимента"
    """
    effective_run_mode = "report+metrics" if args.for_thesis else run_mode

    return ПараметрыЭксперимента(
        run_mode=effective_run_mode,
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
        strict_metrics=bool(args.strict_metrics),
        dry_run=bool(args.dry_run),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Сохраняет словарь в JSON UTF-8 с отступами.

    Аргументы:
        path: путь к итоговому JSON-файлу
        payload: содержимое для сериализации
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _run_preparation_steps(
    paths: ПутиКонвейера,
    experiment: ПараметрыЭксперимента,
) -> list[РезультатШага]:
    """Запускает подготовительные стадии конвейера.

    Аргументы:
        paths: карта путей текущего запуска
        experiment: параметры эксперимента

    Возвращает список результатов шагов
    """
    if experiment.reuse_prepared_data:
        started = datetime.now().isoformat(timespec="seconds")
        finished = datetime.now().isoformat(timespec="seconds")
        return [
            РезультатШага(
                name="reuse_prepared_data",
                command=[],
                status="skipped",
                started_at=started,
                finished_at=finished,
                return_code=0,
                note="Подготовительные шаги пропущены по флагу --reuse-prepared-data.",
            )
        ]

    steps: list[РезультатШага] = []
    python_executable = sys.executable

    normalize_cmd = [
        python_executable,
        str(_script_path(paths.base_dir, "python_script.py")),
        "--data", str(paths.data_dir),
        "--work", str(paths.work_dir),
    ]
    steps.append(_run_command("normalize_raw_exports", normalize_cmd, experiment.dry_run))

    feature_cmd = [
        python_executable,
        str(_script_path(paths.base_dir, "build_features_v2.py")),
        "--work", str(paths.work_dir),
        "--features-dir", str(paths.features_dir),
    ]
    steps.append(_run_command("build_features", feature_cmd, experiment.dry_run))

    preprocess_cmd = [
        python_executable,
        str(_script_path(paths.base_dir, "preprocess_features.py")),
        "--work", str(paths.features_dir),
    ]
    steps.append(_run_command("preprocess_features", preprocess_cmd, experiment.dry_run))

    return steps


def _run_train_and_explain_steps(
    paths: ПутиКонвейера,
    experiment: ПараметрыЭксперимента,
) -> list[РезультатШага]:
    """Запускает train и explain по всем требуемым датам.

    Аргументы:
        paths: карта путей текущего запуска
        experiment: параметры эксперимента

    Возвращает список результатов шагов
    """
    steps: list[РезультатШага] = []
    python_executable = sys.executable

    for current_date in experiment.dates_for_anomalies:
        train_cmd = [
            python_executable,
            str(_script_path(paths.base_dir, "train_anomaly_models.py")),
            "--work", str(paths.features_dir),
            "--out-dir", str(paths.features_dir),
            "--date", current_date,
            "--top", str(experiment.top_anomalies),
            "--contamination", str(experiment.contamination),
            "--n-estimators", str(experiment.n_estimators),
            "--max-samples", str(experiment.max_samples),
            "--n-neighbors", str(experiment.n_neighbors),
            "--random-state", str(experiment.random_state),
        ]
        steps.append(_run_command(f"train_anomaly_models[{current_date}]", train_cmd, experiment.dry_run))

        explain_cmd = [
            python_executable,
            str(_script_path(paths.base_dir, "explain_anomalies.py")),
            "--work", str(paths.features_dir),
            "--anomaly-dir", str(paths.features_dir),
            "--date", current_date,
            "--top-features", str(experiment.top_features),
        ]
        steps.append(_run_command(f"explain_anomalies[{current_date}]", explain_cmd, experiment.dry_run))

    return steps


def _run_report_steps(
    paths: ПутиКонвейера,
    experiment: ПараметрыЭксперимента,
) -> list[РезультатШага]:
    """Запускает визуализацию и SOC-отчёт.

    Аргументы:
        paths: карта путей текущего запуска
        experiment: параметры эксперимента

    Возвращает список результатов шагов
    """
    if experiment.run_mode == "metrics":
        started = datetime.now().isoformat(timespec="seconds")
        finished = datetime.now().isoformat(timespec="seconds")
        return [
            РезультатШага(
                name="report_generation",
                command=[],
                status="skipped",
                started_at=started,
                finished_at=finished,
                return_code=0,
                note="Генерация эксплуатационных отчётов пропущена, так как выбран режим metrics.",
            )
        ]

    steps: list[РезультатШага] = []
    python_executable = sys.executable

    if experiment.scope in {"day", "week", "month"}:
        visualize_cmd = [
            python_executable,
            str(_script_path(paths.base_dir, "visualize_reports.py")),
            "--work", str(paths.features_dir),
            "--report-dir", str(paths.report_output_dir),
            "--scope", experiment.scope,
            "--date", experiment.target_date,
            "--top-pct", str(experiment.top_pct),
            "--contamination", str(experiment.contamination),
            "--n-estimators", str(experiment.n_estimators),
            "--n-neighbors", str(experiment.n_neighbors),
            "--random-state", str(experiment.random_state),
        ]
        steps.append(_run_command("visualize_reports", visualize_cmd, experiment.dry_run))

        soc_cmd = [
            python_executable,
            str(_script_path(paths.base_dir, "soc_report.py")),
            "--work", str(paths.work_dir),
            "--features-dir", str(paths.features_dir),
            "--anomaly-dir", str(paths.features_dir),
            "--report-dir", str(paths.report_output_dir),
            "--scope", experiment.scope,
            "--date", experiment.target_date,
        ]
        steps.append(_run_command("soc_report", soc_cmd, experiment.dry_run))
        return steps

    for current_date in experiment.dates_for_anomalies:
        visualize_cmd = [
            python_executable,
            str(_script_path(paths.base_dir, "visualize_reports.py")),
            "--work", str(paths.features_dir),
            "--report-dir", str(paths.report_output_dir),
            "--scope", "day",
            "--date", current_date,
            "--top-pct", str(experiment.top_pct),
            "--contamination", str(experiment.contamination),
            "--n-estimators", str(experiment.n_estimators),
            "--n-neighbors", str(experiment.n_neighbors),
            "--random-state", str(experiment.random_state),
        ]
        steps.append(_run_command(f"visualize_reports[{current_date}]", visualize_cmd, experiment.dry_run))

        soc_cmd = [
            python_executable,
            str(_script_path(paths.base_dir, "soc_report.py")),
            "--work", str(paths.work_dir),
            "--features-dir", str(paths.features_dir),
            "--anomaly-dir", str(paths.features_dir),
            "--report-dir", str(paths.report_output_dir),
            "--scope", "day",
            "--date", current_date,
        ]
        steps.append(_run_command(f"soc_report[{current_date}]", soc_cmd, experiment.dry_run))

    return steps


def _run_metrics_step(
    paths: ПутиКонвейера,
    experiment: ПараметрыЭксперимента,
) -> tuple[list[РезультатШага], list[str]]:
    """Подключает внешний модуль прокси-метрик качества, если он существует.

    Аргументы:
        paths: карта путей текущего запуска
        experiment: параметры эксперимента

    Возвращает:
        Кортеж (steps, warnings), где steps — результаты выполненных шагов,
        warnings — предупреждения по отсутствующим или пропущенным метрикам
    """
    steps: list[РезультатШага] = []
    warnings: list[str] = []

    if experiment.run_mode not in {"metrics", "report+metrics"}:
        started = datetime.now().isoformat(timespec="seconds")
        finished = datetime.now().isoformat(timespec="seconds")
        steps.append(
            РезультатШага(
                name="proxy_metrics",
                command=[],
                status="skipped",
                started_at=started,
                finished_at=finished,
                return_code=0,
                note="Расчёт метрик качества не запрашивался текущим режимом запуска.",
            )
        )
        return steps, warnings

    metrics_script_path = _script_path(paths.base_dir, experiment.metrics_script)
    if not metrics_script_path.exists():
        warning_text = (
            f"Скрипт расчёта прокси-метрик не найден: {metrics_script_path}. "
            "Точка интеграции сохранена, но шаг не был выполнен."
        )
        warnings.append(warning_text)

        if experiment.strict_metrics:
            raise FileNotFoundError(warning_text)

        started = datetime.now().isoformat(timespec="seconds")
        finished = datetime.now().isoformat(timespec="seconds")
        steps.append(
            РезультатШага(
                name="proxy_metrics",
                command=[sys.executable, str(metrics_script_path)],
                status="skipped",
                started_at=started,
                finished_at=finished,
                return_code=0,
                note=warning_text,
            )
        )
        return steps, warnings

    metrics_cmd = [
        sys.executable,
        str(metrics_script_path),
        "--work", str(paths.features_dir),
        "--anomaly-dir", str(paths.features_dir),
        "--report-dir", str(paths.metrics_dir),
        "--scope", experiment.scope,
        "--date", experiment.target_date,
        "--top-k", str(experiment.top_anomalies),
        "--contamination", str(experiment.contamination),
        "--n-estimators", str(experiment.n_estimators),
        "--n-neighbors", str(experiment.n_neighbors),
        "--random-state", str(experiment.random_state),
    ]
    steps.append(_run_command("proxy_metrics", metrics_cmd, experiment.dry_run))
    return steps, warnings


def _build_manifest(
    started_at: str,
    finished_at: str,
    paths: ПутиКонвейера,
    experiment: ПараметрыЭксперимента,
    step_results: list[РезультатШага],
    warnings: list[str],
) -> МанифестЗапуска:
    """Формирует manifest текущего запуска.

    Аргументы:
        started_at: время старта orchestrator
        finished_at: время завершения orchestrator
        paths: карта путей проекта
        experiment: параметры эксперимента
        step_results: выполненные шаги
        warnings: предупреждения orchestrator

    Возвращает экземпляр "МанифестЗапуска"
    """
    return МанифестЗапуска(
        started_at=started_at,
        finished_at=finished_at,
        paths={
            "base_dir": str(paths.base_dir),
            "data_dir": str(paths.data_dir),
            "work_dir": str(paths.work_dir),
            "features_dir": str(paths.features_dir),
            "report_root_dir": str(paths.report_root_dir),
            "run_dir": str(paths.run_dir),
            "report_output_dir": str(paths.report_output_dir),
            "meta_dir": str(paths.meta_dir),
            "metrics_dir": str(paths.metrics_dir),
        },
        experiment=asdict(experiment),
        steps=[asdict(step_result) for step_result in step_results],
        warnings=warnings,
    )


def main() -> int:
    """Точка входа orchestrator.

    Функция:
      1) считывает CLI-параметры и/или запрашивает недостающие значения;
      2) запускает обязательные стадии подготовки данных;
      3) определяет доступные даты и формирует окно анализа;
      4) выполняет train/explain/report-steps;
      5) по запросу подключает модуль прокси-метрик;
      6) сохраняет конфигурацию и manifest запуска.

    Возвращает код завершения процесса: 0 при успехе.
    """
    orchestrator_started_at = datetime.now().isoformat(timespec="seconds")
    args = _parse_args()
    _validate_cli_values(args)

    scope, run_mode, target_date, start_date, end_date = _resolve_runtime_choices(args)
    base_dir = Path(__file__).resolve().parent

    data_dir = _resolve_path(base_dir, args.data_dir)
    work_dir = _resolve_path(base_dir, args.work_dir)
    features_dir = _resolve_path(base_dir, args.features_dir)
    report_root_dir = _resolve_path(base_dir, args.report_dir)

    preparation_paths = ПутиКонвейера(
        base_dir=base_dir,
        data_dir=data_dir,
        work_dir=work_dir,
        features_dir=features_dir,
        report_root_dir=report_root_dir,
        run_dir=report_root_dir,
        report_output_dir=report_root_dir,
        meta_dir=report_root_dir,
        metrics_dir=report_root_dir,
    )

    step_results: list[РезультатШага] = []
    warnings: list[str] = []

    preparation_experiment = _build_experiment_parameters(
        args=args,
        scope=scope,
        run_mode=run_mode,
        target_date=target_date or "pending",
        dates_for_anomalies=[],
    )
    step_results.extend(_run_preparation_steps(preparation_paths, preparation_experiment))

    available_dates = _load_available_dates(preparation_paths.features_dir)
    resolved_target_date, dates_for_anomalies = _resolve_dates_for_scope(
        scope=scope,
        target_date=target_date,
        start_date=start_date,
        end_date=end_date,
        available_dates=available_dates,
    )

    paths = _build_paths(
        base_dir=base_dir,
        args=args,
        scope=scope,
        target_date=resolved_target_date,
        run_mode=("report+metrics" if args.for_thesis else run_mode),
    )

    experiment = _build_experiment_parameters(
        args=args,
        scope=scope,
        run_mode=run_mode,
        target_date=resolved_target_date,
        dates_for_anomalies=dates_for_anomalies,
    )

    requested_run_payload = {
        "scope": scope,
        "run_mode": experiment.run_mode,
        "input_date": target_date,
        "input_start_date": start_date,
        "input_end_date": end_date,
        "resolved_target_date": resolved_target_date,
        "resolved_dates_for_anomalies": dates_for_anomalies,
        "for_thesis": bool(args.for_thesis),
    }
    _write_json(paths.meta_dir / "requested_run.json", requested_run_payload)
    _write_json(paths.meta_dir / "run_config.json", asdict(experiment))

    step_results.extend(_run_train_and_explain_steps(paths, experiment))
    step_results.extend(_run_report_steps(paths, experiment))

    metrics_steps, metrics_warnings = _run_metrics_step(paths, experiment)
    step_results.extend(metrics_steps)
    warnings.extend(metrics_warnings)

    orchestrator_finished_at = datetime.now().isoformat(timespec="seconds")
    manifest = _build_manifest(
        started_at=orchestrator_started_at,
        finished_at=orchestrator_finished_at,
        paths=paths,
        experiment=experiment,
        step_results=step_results,
        warnings=warnings,
    )
    _write_json(paths.meta_dir / "manifest.json", asdict(manifest))

    print("\nГотово: полный цикл выполнен успешно.")
    print(f"Директория запуска: {paths.run_dir}")
    print(f"Manifest: {paths.meta_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
