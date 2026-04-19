# FQW_diplom

Эксплуатационный README для запуска пайплайна обнаружения поведенческих аномалий по SIEM- и NGFW-логам.

## Назначение

Проект реализует офлайн-конвейер обработки выгрузок SIEM/NGFW:
- нормализация и анонимизация сырых событий;
- построение признаков `user/day` и `host/day`;
- очистка признаков;
- поиск аномалий с помощью `Isolation Forest` и `Local Outlier Factor`;
- explainability-слой для интерпретации причин аномалии;
- построение графиков и SOC-отчётов;
- расчёт прокси-метрик качества без разметки.

Основная точка входа для полного запуска:
- `script/full_cycle_auto_evolute_metrics.py`

## Структура проекта

По текущей структуре репозитория верхний уровень выглядит так:

```text
FQW_diplom/
├── .git/
├── .idea/
├── .venv/
├── screens/
├── script/
├── version/
├── README.md
├── .gitignore
└── .gitattributes
```

Рабочая часть проекта находится в каталоге `script/`:

```text
script/
├── data/                             # сырые выгрузки SIEM/NGFW (*.tsv, *.txt)
├── python_script.py                  # нормализация и анонимизация
├── build_features_v2.py              # построение признаков
├── preprocess_features.py            # очистка признаков
├── train_anomaly_models.py           # скоринг аномалий
├── explain_anomalies.py              # explainability-слой
├── visualize_reports.py              # графики day/week/month
├── soc_report.py                     # SOC-отчёт с контекстом
├── evaluate_proxy_metrics.py         # прокси-метрики качества без разметки
├── viz_core.py                       # общие функции скоринга и визуализации
├── auto_generate_reports.py          # пакетная генерация базовых отчётов
└── full_cycle_auto_evolute_metrics.py# основной orchestrator полного цикла
```

## Что нужно для запуска

Минимально необходимо:
- Python 3.10+;
- установленные библиотеки `pandas`, `numpy`, `scikit-learn`, `matplotlib`;
- исходные выгрузки SIEM/NGFW в папке `script/data/`.

Установка зависимостей:

```bash
pip install -U pandas numpy scikit-learn matplotlib
```

## Какие данные должны лежать в `script/data/`

В папку `script/data/` помещаются сырые выгрузки:
- `*.tsv`
- `*.txt`

Ожидается, что это исходные экспортированные данные SIEM и, при наличии, события NGFW/Palo Alto.

## Какие папки должны быть заранее

Обязательно должна существовать и быть заполнена:
- `script/data/`

Остальные рабочие каталоги при обычном запуске могут отсутствовать. Скрипты создадут их автоматически:
- `script/work/`
- `script/features/`
- `script/report/`

Также для каждого запуска `full_cycle_auto_evolute_metrics.py` автоматически создаёт отдельный каталог артефактов.

## Что создаётся в процессе работы

### `script/work/`
Промежуточные нормализованные суточные CSV:
- `userXXX_SIEM_YYYY-MM-DD.csv`
- `userXXX_PAN_YYYY-MM-DD.csv`
- `<hostname>_SIEM_YYYY-MM-DD.csv`
- `<hostname>_PAN_YYYY-MM-DD.csv`
- `user_mapping.csv`

### `script/features/`
Таблицы признаков:
- `features_users.csv`
- `features_hosts.csv`
- `features_users_clean.csv`
- `features_hosts_clean.csv`

### `script/report/<run_id>/`
Единый каталог артефактов одного запуска:

```text
script/report/<run_id>/
├── anomalies/   # anomalies_*.csv, *_explain.csv, meta.json
├── reports/     # графики и SOC-отчёты
├── metrics/     # прокси-метрики, CSV/JSON/PNG
└── meta/        # requested_run.json, run_config.json, manifest.json
```

## Полный запуск

Из корня репозитория:

```bash
cd script
python full_cycle_auto_evolute_metrics.py
```

Скрипт поддерживает интерактивный режим:
- выбор масштаба: `day`, `week`, `month`, `range`, `all`;
- выбор режима: `report`, `metrics`, `report+metrics`;
- ввод даты или диапазона дат.

## Рекомендуемый первый запуск

Для первого полного прогона:

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope month --date 2025-12-31 --run-mode report+metrics
```

Этот запуск:
- подготовит данные из `data/`;
- построит признаки;
- посчитает аномалии;
- сформирует explainability;
- построит графики и SOC-отчёт;
- посчитает прокси-метрики качества;
- сохранит всё в отдельный каталог внутри `script/report/`.

## Примеры запуска

### За один день

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope day --date 2025-12-31 --run-mode report+metrics
```

### За неделю

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope week --date 2025-12-31 --run-mode report+metrics
```

### За месяц

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope month --date 2025-12-31 --run-mode report+metrics
```

### За заданный диапазон

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope range --start-date 2025-12-01 --end-date 2025-12-31 --run-mode report+metrics
```

### За всё доступное время

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope all --run-mode report+metrics
```

## Если данные уже подготовлены

Если каталоги `work/` и `features/` уже содержат актуальные результаты и вы не хотите заново запускать нормализацию и построение признаков:

```bash
cd script
python full_cycle_auto_evolute_metrics.py --scope month --date 2025-12-31 --run-mode report+metrics --reuse-prepared-data
```

В этом режиме должны уже существовать:
- `features_users_clean.csv`
- `features_hosts_clean.csv`

## Что означает каждый этап пайплайна

1. `python_script.py`  
   Нормализует сырые выгрузки, удаляет служебные поля, анонимизирует пользователей и раскладывает события по суткам.

2. `build_features_v2.py`  
   Агрегирует события в признаки `user/day` и `host/day`.

3. `preprocess_features.py`  
   Приводит признаки к числовому виду и заполняет пропуски.

4. `train_anomaly_models.py`  
   Обучает `Isolation Forest` и `LOF` на исторических днях и считает аномалии целевой даты.

5. `explain_anomalies.py`  
   Вычисляет признаки, сильнее всего отклонившиеся от базовой линии.

6. `visualize_reports.py`  
   Строит графики за день, неделю или месяц.

7. `soc_report.py`  
   Формирует SOC-отчёт с контекстом по событиям.

8. `evaluate_proxy_metrics.py`  
   Считает прокси-метрики качества без разметки:
   - `Jaccard@K`
   - `Overlap@K`
   - `Spearman@K`
   - распределение `score_combined_norm`
   - частоту признаков из explainability.

## Что искать после запуска

После завершения полного запуска сначала проверьте:
- `script/report/<run_id>/meta/manifest.json` — общий статус запуска;
- `script/report/<run_id>/reports/` — графики и SOC-отчёты;
- `script/report/<run_id>/metrics/` — таблицы и графики для ВКР;
- `script/report/<run_id>/anomalies/` — CSV с аномалиями и explainability.

## Назначение прокси-метрик качества

`evaluate_proxy_metrics.py` используется для оценки модели в условиях отсутствия размеченного ground truth. На выходе формируются:
- таблицы устойчивости top-K аномалий;
- histogram распределения аномальных score;
- графики устойчивости при варьировании `contamination` и `n_neighbors`;
- диаграммы частоты факторов explainability.

Эти материалы предназначены для главы «Экспериментальная оценка» ВКР.

## Источник данных

Данные получены из SIEM KUMA (Kaspersky). Перед использованием их необходимо обезличить. Это выполняет `python_script.py`, который преобразует реальные учётные записи в формат `userXXX`.

## Автор

**Автор:** В. С. Новиков  
**Научный руководитель:** Д. В. Смирнов
