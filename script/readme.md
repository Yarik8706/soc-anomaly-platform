# Документация по скриптам проекта обнаружения поведенческих аномалий

В каталоге собраны описания основных скриптов пайплайна обработки SIEM/NGFW-логов,
построения признаков, поиска аномалий, explainability, SOC-отчётности и расчёта
прокси-метрик качества без размеченных данных.

## Актуальная точка входа

Основной orchestrator проекта:

- `full_cycle_auto_evolute_metrics.py`

Именно этот скрипт рекомендуется использовать для полного запуска конвейера,
так как он объединяет:
- подготовку данных;
- построение признаков;
- скоринг аномалий;
- explainability;
- графические отчёты;
- SOC-отчёт;
- прокси-метрики качества модели.

Скрипт поддерживает режимы `report`, `metrics`, `report+metrics`, а также масштабы
`day`, `week`, `month`, `range`, `all`. Для каждого запуска он создаёт единый каталог
артефактов с подкаталогами `anomalies/`, `reports/`, `metrics/`, `meta/`. fileciteturn18file15 fileciteturn18file19

## Базовая структура проекта

```text
project/
├── full_cycle_auto_evolute_metrics.py
├── evaluate_proxy_metrics.py
├── python_script.py
├── build_features_v2.py
├── preprocess_features.py
├── train_anomaly_models.py
├── explain_anomalies.py
├── visualize_reports.py
├── soc_report.py
├── auto_generate_reports.py
├── viz_core.py
├── data/
├── work/
├── features/
└── report/
```

## Назначение каталогов

- `data/` — сырые выгрузки SIEM/NGFW в форматах `*.tsv` и `*.txt`. fileciteturn17file5
- `work/` — нормализованные суточные CSV и `user_mapping.csv`. fileciteturn17file5
- `features/` — таблицы признаков и очищенные таблицы `features_*_clean.csv`. fileciteturn17file4
- `report/` — корневая папка запусков orchestrator.

## Артефакты одного запуска orchestrator

Пример структуры одного запуска:

```text
report/<scope>__<target_date>__<timestamp>[/<tag>]/
├── anomalies/
├── reports/
├── metrics/
└── meta/
```

Где:
- `anomalies/` — TOP-N аномалий, explain-файлы и метаданные train-этапа;
- `reports/` — PNG-графики `visualize_reports.py` и Markdown/SOC-артефакты;
- `metrics/` — прокси-метрики качества, CSV/JSON/PNG из `evaluate_proxy_metrics.py`;
- `meta/` — `requested_run.json`, `run_config.json`, `manifest.json`. fileciteturn18file15 fileciteturn18file19

## Основные зависимости

```bash
pip install -U pandas scikit-learn matplotlib numpy
```

## Типовые сценарии запуска

### Полный запуск за один день

```bash
python full_cycle_auto_evolute_metrics.py --scope day --date 2025-12-31 --run-mode report+metrics
```

### Полный запуск за месяц

```bash
python full_cycle_auto_evolute_metrics.py --scope month --date 2025-12-31 --run-mode report+metrics
```

### Запуск только оценочных метрик на уже подготовленных признаках

```bash
python full_cycle_auto_evolute_metrics.py --scope day --date 2025-12-31 --run-mode metrics --reuse-prepared-data
```

### Прямой запуск модуля прокси-метрик

```bash
python evaluate_proxy_metrics.py --work ./features --date 2025-12-31 --out-dir ./report/metrics
```

## Перечень документации

- `python_script.md`
- `build_features_v2.md`
- `preprocess_features.md`
- `train_anomaly_models.md`
- `explain_anomalies.md`
- `visualize_reports.md`
- `soc_report.md`
- `auto_generate_reports.md`
- `viz_core.md`
- `full_cycle.md` — описание исторической точки входа `full_cycle.py`
- `full_cycle_auto_evolute_metrics.md` — описание актуального orchestrator
- `evaluate_proxy_metrics.md` — описание модуля прокси-метрик качества
