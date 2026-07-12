# full_cycle_auto_evolute_metrics.py

## Назначение

`full_cycle_auto_evolute_metrics.py` — актуальная единая точка входа проекта.
Скрипт выступает orchestrator полного конвейера и объединяет:

1. нормализацию сырых выгрузок SIEM/NGFW;
2. построение признаков пользователей и хостов;
3. препроцессинг признаков;
4. расчёт аномалий по выбранным датам;
5. explainability-слой;
6. графические отчёты и SOC-отчётность;
7. прокси-метрики качества модели без разметки;
8. фиксацию конфигурации и результатов запуска в JSON. fileciteturn18file15 fileciteturn18file19

## Ключевые возможности

- поддержка CLI и интерактивного режима;
- масштабы запуска:
  - `day`
  - `week`
  - `month`
  - `range`
  - `all`
- режимы запуска:
  - `report`
  - `metrics`
  - `report+metrics`
- исследовательский флаг `--for-thesis`;
- пропуск ранних этапов по флагу `--reuse-prepared-data`;
- единый каталог артефактов одного запуска.

## Основные dataclass-структуры

### `PipelinePaths`
Описывает каталоги, используемые orchestrator:
- `base_dir`
- `data_dir`
- `work_dir`
- `features_dir`
- `report_root_dir`
- `run_dir`
- `anomalies_dir`
- `reports_dir`
- `metrics_dir`
- `meta_dir`

### `ExperimentConfig`
Хранит параметры текущего запуска:
- `run_mode`
- `scope`
- `target_date`
- `dates_for_anomalies`
- `top_anomalies`
- `top_features`
- `top_pct`
- `contamination`
- `n_estimators`
- `max_samples`
- `n_neighbors`
- `random_state`
- `for_thesis`
- `reuse_prepared_data`
- параметры блока метрик:
  - `metrics_script`
  - `metrics_k_list`
  - `metrics_plot_k`
  - `metrics_contamination_grid`
  - `metrics_neighbors_grid`
  - `contributor_severities`
  - `strict_metrics`
  - `strict_explain`
  - `save_score_tables`
- `dry_run`
- `run_tag`

### `StepResult`
Описывает результат одного шага orchestrator:
- имя шага;
- команда;
- статус;
- время старта и завершения;
- код возврата;
- пояснение.

### `RunManifest`
Финальная сводка одного запуска.

## Основные функции

- `_parse_args()` — разбор CLI-аргументов;
- `_resolve_scope()` — определение масштаба запуска;
- `_resolve_run_mode()` — определение режима запуска;
- `_resolve_requested_dates()` — обработка пользовательских дат;
- `_load_available_dates()` — загрузка доступных дат по очищенным признакам;
- `_resolve_target_and_dates()` — определение целевой даты и списка дат для train/explain;
- `_build_run_id()` — формирование уникального идентификатора запуска;
- `_prepare_paths()` — создание структуры каталогов артефактов;
- `_run_prepare_stage()` — запуск `python_script.py`, `build_features_v2.py`, `preprocess_features.py`;
- `_run_train_and_explain()` — запуск `train_anomaly_models.py` и `explain_anomalies.py`;
- `_run_reporting()` — запуск `visualize_reports.py` и `soc_report.py`;
- `_run_proxy_metrics()` — запуск `evaluate_proxy_metrics.py`;
- `_build_manifest()` — формирование итогового manifest;
- `main()` — точка входа.

## Входные данные

### Обязательные скрипты рядом с orchestrator
- `python_script.py`
- `build_features_v2.py`
- `preprocess_features.py`
- `train_anomaly_models.py`
- `explain_anomalies.py`
- `visualize_reports.py`
- `soc_report.py`
- `evaluate_proxy_metrics.py`
- `viz_core.py`

### Исходные данные
- каталог `data/` со сырыми выгрузками `*.tsv` / `*.txt`, если не используется `--reuse-prepared-data`.

### CLI-аргументы

#### Управление областью анализа
- `--scope {day,week,month,range,all}`
- `--date YYYY-MM-DD`
- `--start-date YYYY-MM-DD`
- `--end-date YYYY-MM-DD`

#### Управление режимом запуска
- `--run-mode {report,metrics,report+metrics}`
- `--for-thesis`
- `--dry-run`

#### Каталоги
- `--data-dir`
- `--work-dir`
- `--features-dir`
- `--report-dir`
- `--run-tag`

#### Поведение пайплайна
- `--reuse-prepared-data`
- `--top-anomalies`
- `--top-features`
- `--top-pct`
- `--contamination`
- `--n-estimators`
- `--max-samples`
- `--n-neighbors`
- `--random-state`

#### Параметры модуля метрик
- `--metrics-script`
- `--metrics-k-list`
- `--metrics-plot-k`
- `--metrics-contamination-grid`
- `--metrics-neighbors-grid`
- `--contributor-severities`
- `--strict-metrics`
- `--strict-explain`
- `--save-score-tables`

## Выходные данные

Для каждого запуска создаётся каталог:

```text
report/<scope>__<target_date>__<timestamp>[/<tag>]/
```

Внутри создаются подкаталоги:

### `anomalies/`
- `anomalies_users_<date>.csv`
- `anomalies_hosts_<date>.csv`
- `anomalies_users_<date>_explain.csv`
- `anomalies_hosts_<date>_explain.csv`
- `anomalies_all_<date>_explain.csv`
- `*_meta.json`

### `reports/`
- PNG-графики `visualize_reports.py`
- Markdown и CSV из `soc_report.py`

### `metrics/`
- CSV/JSON/PNG из `evaluate_proxy_metrics.py`

### `meta/`
- `requested_run.json`
- `run_config.json`
- `manifest.json`

## Примеры запуска

### Один день: полный запуск
```bash
python full_cycle_auto_evolute_metrics.py --scope day --date 2025-12-31 --run-mode report+metrics
```

### Один месяц: полный запуск
```bash
python full_cycle_auto_evolute_metrics.py --scope month --date 2025-12-31 --run-mode report+metrics
```

### Только оценочные метрики по уже подготовленным данным
```bash
python full_cycle_auto_evolute_metrics.py --scope day --date 2025-12-31 --run-mode metrics --reuse-prepared-data
```

### Диапазон дат для ВКР
```bash
python full_cycle_auto_evolute_metrics.py --scope range --start-date 2025-12-01 --end-date 2025-12-31 --for-thesis
```

## Особенности интерпретации scope

- `day` — анализ только одной даты;
- `week` — окно 7 дней до заданной конечной даты;
- `month` — окно 30 дней до заданной конечной даты;
- `range` — все доступные даты в заданном диапазоне;
- `all` — все доступные даты признаков.

## Практическая роль в проекте

Этот скрипт рекомендуется использовать:
- для регулярного запуска всего пайплайна;
- для воспроизводимых экспериментов в рамках ВКР;
- для формирования единого каталога артефактов без ручного запуска нескольких модулей.
