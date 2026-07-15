# SOC Anomaly Platform

Веб-приложение для автоматизации работы ИБ/SOC-специалиста.

## Цель

Загрузка SIEM/NGFW-логов, запуск ML-анализа, поиск аномалий пользователей и хостов, explainability и SOC-отчеты.

## Планируемые модули

- Data Ingestion
- Analysis Pipeline
- Analyst Workspace
- Reporting & Metrics
- Security & Operations

## Обработка входных логов

Backend принимает `.csv`, `.tsv` и `.txt` файлы и хранит историю их обработки.
Основные операции:

- `GET /uploads` — история загрузок с результатами проверки и нормализации;
- `POST /uploads/{file_id}/validate` — определение кодировки, разделителя и колонок;
- `POST /uploads/{file_id}/normalize` — формирование дневных SIEM/PAN CSV;
- `GET /uploads/{file_id}` — текущее состояние и ссылки на созданные артефакты.

Нормализация удаляет служебные tenant/cluster-поля, приводит время к единому формату,
анонимизирует пользователей и сохраняет отдельные файлы по датам. Каталоги входных
и нормализованных данных задаются переменными `UPLOAD_DIRECTORY` и
`NORMALIZED_DIRECTORY`.
