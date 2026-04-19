# evaluate_proxy_metrics.py

## Назначение

`evaluate_proxy_metrics.py` — исследовательский модуль оценки качества безнадзорной
модели обнаружения аномалий в условиях отсутствия эталонной разметки.

Скрипт отвечает не за эксплуатационный SOC-отчёт, а за формирование материалов для
экспериментальной главы ВКР:
- внутренних метрик по распределению anomaly score;
- метрик устойчивости верхней части ранга;
- агрегированного анализа explainability-признаков;
- графиков, пригодных для включения в текст работы.

## Почему нужен отдельный модуль

`train_anomaly_models.py` экспортирует только TOP-N аномалий, чего недостаточно для:
- анализа полного распределения score;
- построения гистограмм по всем сущностям дня;
- корректного расчёта устойчивости top-K при варьировании гиперпараметров.

Поэтому `evaluate_proxy_metrics.py` напрямую использует `viz_core.score_day()` и
строит полный дневной скоринг по всем сущностям выбранной даты. fileciteturn18file13

## Основные задачи

1. Рассчитать полный дневной скоринг для `users` и `hosts`.
2. Оценить распределение `score_combined_norm`.
3. Посчитать метрики устойчивости при изменении:
   - `contamination`
   - `n_neighbors`
4. Агрегировать признаки, чаще всего попадающие в `top_contributors`.
5. Сохранить CSV, JSON и PNG-графики.
6. Вывести краткую консольную сводку.

## Поддерживаемые метрики

### Метрики по распределению score
- `rows_total`
- `score_mean`
- `score_std`
- `score_median`
- `score_p90`
- `score_p95`
- `score_p99`
- `tail_gap_p95_median`
- `tail_ratio_p95_median`
- `critical_count`
- `high_count`
- `medium_count`
- `low_count`

### Метрики устойчивости верхней части ранга
Для каждого значения `K` из списка `--k-list` рассчитываются:

- `Jaccard@K`
- `Overlap@K`
- `Spearman@K`

#### Определения
- **Jaccard@K** — сходство множеств top-K между базовой и альтернативной конфигурацией;
- **Overlap@K** — доля совпадающих объектов в верхней части ранга;
- **Spearman@K** — устойчивость относительного порядка сущностей в top-K.

### Explainability-агрегация
По explain-файлам рассчитываются частоты признаков, чаще всего встречающихся среди:
- `critical`
- `high`
или других severity, заданных через `--contributor-severities`.

## Основные структуры и функции

### `ExperimentConfig`
Конфигурация запуска модуля. Хранит:
- `work_dir`
- `anomaly_dir`
- `out_dir`
- `target_date`
- `contamination`
- `n_estimators`
- `n_neighbors`
- `random_state`
- `ks`
- `plot_k`
- `contamination_grid`
- `neighbors_grid`
- `contributor_severities`
- `strict_explain`
- `save_score_tables`

### Подготовка параметров
- `_parse_float_list()`
- `_parse_int_list()`
- `_normalize_date()`
- `_pick_latest_date()`
- `_coerce_path()`
- `_build_config()`

### Работа с explainability
- `_read_explain_file()`
- `_aggregate_contributors()`

### Работа с rank-метриками
- `_top_k_entities()`
- `_rank_map()`
- `_jaccard_at_k()`
- `_overlap_at_k()`
- `_spearman_at_k()`

### Работа с распределением score
- `_safe_numeric()`
- `_score_summary()`
- `_run_scores_for_day()`

### Устойчивость модели
- `_stability_against_contamination()`
- `_stability_against_neighbors()`
- `_mean_metric_for_group()`
- `_build_proxy_metrics_table()`

### Визуализация
- `_save_score_histogram()`
- `_save_stability_plot()`
- `_save_contributors_plot()`

### Вывод результатов
- `_scores_to_console_brief()`
- `_run_one_kind()`
- `_save_json()`
- `main()`

## Входные данные

### Обязательные
- `features_users_clean.csv`
- `features_hosts_clean.csv`

### Опциональные
- `anomalies_users_YYYY-MM-DD_explain.csv`
- `anomalies_hosts_YYYY-MM-DD_explain.csv`

Если explain-файлы отсутствуют и `--strict-explain` не задан, скрипт всё равно
отработает, но explainability-блок будет пустым.

## CLI-аргументы

### Базовые
- `--work` — каталог с очищенными признаками;
- `--anomaly-dir` — каталог explain-файлов;
- `--out-dir` — каталог выходных артефактов;
- `--date` — целевая дата `YYYY-MM-DD`.

### Параметры базовой модели
- `--contamination`
- `--n-estimators`
- `--n-neighbors`
- `--random-state`

### Параметры устойчивости
- `--k-list` — список значений `K`, например `10,20`;
- `--plot-k` — значение `K` для графиков устойчивости;
- `--contamination-grid` — сетка значений contamination;
- `--neighbors-grid` — сетка значений n_neighbors.

### Explainability
- `--contributor-severities` — какие уровни severity анализировать;
- `--strict-explain` — считать отсутствие explain-файлов ошибкой.

### Дополнительно
- `--save-score-tables` — сохранять полные дневные таблицы скоринга.

## Выходные файлы

### Таблицы
- `proxy_metrics_users_YYYY-MM-DD.csv`
- `proxy_metrics_hosts_YYYY-MM-DD.csv`
- `stability_users_YYYY-MM-DD.csv`
- `stability_hosts_YYYY-MM-DD.csv`
- `contributors_users_YYYY-MM-DD.csv`
- `contributors_hosts_YYYY-MM-DD.csv`
- `day_scores_users_YYYY-MM-DD.csv` — если задан `--save-score-tables`
- `day_scores_hosts_YYYY-MM-DD.csv` — если задан `--save-score-tables`

### JSON
- `proxy_metrics_summary_YYYY-MM-DD.json`

### Графики для ВКР
- `score_hist_users_YYYY-MM-DD.png`
- `score_hist_hosts_YYYY-MM-DD.png`
- `stability_contamination_users_YYYY-MM-DD.png`
- `stability_contamination_hosts_YYYY-MM-DD.png`
- `stability_neighbors_users_YYYY-MM-DD.png`
- `stability_neighbors_hosts_YYYY-MM-DD.png`
- `contributors_freq_users_YYYY-MM-DD.png`
- `contributors_freq_hosts_YYYY-MM-DD.png`

## Консольный вывод

После запуска по каждому типу сущности (`users`, `hosts`) печатается краткая сводка:
- дата;
- число строк в анализе;
- `tail_ratio_p95_median`;
- число `critical` и `high`;
- значения `Jaccard@K`, `Overlap@K`, `Spearman@K` по `contamination`;
- значения `Jaccard@K`, `Overlap@K`, `Spearman@K` по `n_neighbors`;
- наиболее частые explain-признаки.

## Примеры запуска

### Базовый запуск
```bash
python evaluate_proxy_metrics.py --work ./features --date 2025-12-31
```

### Сохранение в отдельный каталог
```bash
python evaluate_proxy_metrics.py --work ./features --date 2025-12-31 --out-dir ./report/metrics
```

### Расчёт для нескольких значений K
```bash
python evaluate_proxy_metrics.py --work ./features --date 2025-12-31 --k-list 10,20
```

### Строгий режим explainability
```bash
python evaluate_proxy_metrics.py --work ./features --anomaly-dir ./anomalies --date 2025-12-31 --strict-explain
```

### Сохранение полных таблиц score
```bash
python evaluate_proxy_metrics.py --work ./features --date 2025-12-31 --save-score-tables
```

## Роль в полном цикле

При запуске через `full_cycle_auto_evolute_metrics.py` этот модуль вызывается
автоматически в режимах:
- `metrics`
- `report+metrics`
- `--for-thesis`

В таком случае результаты складываются в `report/<run_id>/metrics/`, а конфигурация
его запуска фиксируется в `meta/run_config.json` и `meta/manifest.json`. fileciteturn18file19
