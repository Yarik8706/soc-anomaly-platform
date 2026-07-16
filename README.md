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

## Локальный запуск backend

Требования: Docker с Compose v2. Backend, PostgreSQL, Redis, RQ worker, миграции и
начальный администратор запускаются одной командой:

```bash
docker compose up --build
```

При первом запуске сервис `migrations` применяет все Alembic-миграции и создаёт
локального администратора. Значения по умолчанию предназначены только для локальной
разработки:

- email: `admin@example.com`;
- password: `local-admin-change-me`.

Перед использованием общей среды скопируйте `.env.example` в `.env` и обязательно
замените `JWT_SECRET` и `INITIAL_ADMIN_PASSWORD`. Seed идемпотентен и не меняет
пароль уже существующего администратора.

После запуска доступны:

- API и Swagger UI: <http://localhost:8001/docs>;
- healthcheck: <http://localhost:8001/health>.

Порт API можно изменить, например: `BACKEND_PORT=9000 docker compose up --build`.

PostgreSQL и Redis доступны backend/worker по внутренней сети Compose и по
умолчанию не публикуются на host, чтобы не конфликтовать с локальными сервисами.

Проверить состояние и посмотреть логи worker:

```bash
docker compose ps
docker compose logs -f worker
```

Остановить контейнеры без удаления данных:

```bash
docker compose down
```

Frontend пока не входит в Compose: его инициализация отслеживается отдельной
задачей `MYO-58`. После появления production-сборки frontend добавляется отдельным
сервисом, не меняя контур `backend`/`worker`/`postgres`/`redis`.
