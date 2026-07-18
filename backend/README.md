# Локальная разработка backend

Backend состоит из FastAPI-приложения, PostgreSQL, Redis, RQ worker и Alembic-миграций.
Ниже описаны два варианта запуска: вся платформа в Docker и инфраструктура в Docker с
backend-процессами на хосте.

## Требования

- Docker с Compose v2;
- для запуска Python-процессов на хосте — Python 3.14 и Poetry 2.

## Вариант 1: весь стек в Docker

Из корня репозитория выполните:

```bash
docker compose up --build
```

Compose запустит PostgreSQL, Redis, миграции, API, RQ worker и frontend. При первом
запуске миграции также создадут тестового администратора:

- email: `admin@admin.com`;
- пароль: `admin`.

API будет доступен на <http://localhost:8001>, Swagger UI — на
<http://localhost:8001/docs>, healthcheck — на <http://localhost:8001/health>.

Полезные команды:

```bash
docker compose ps
docker compose logs -f backend worker migrations
docker compose down
```

`docker compose down` сохраняет данные в Docker volumes. Чтобы полностью удалить
локальные базы PostgreSQL и Redis, используйте `docker compose down -v`; эта команда
необратимо удаляет локальные данные инфраструктуры.

## Вариант 2: PostgreSQL и Redis в Docker, backend на хосте

1. Из корня репозитория поднимите инфраструктуру:

   ```bash
   docker compose up -d postgres redis
   ```

2. Установите Python-зависимости:

   ```bash
   cd backend
   poetry install
   cd ..
   ```

3. Настройте локальный файл окружения в корне репозитория. Если `.env` ещё нет,
   создайте его из примера:

   ```bash
   test -f .env || cp .env.example .env
   ```

   Для процессов на хосте используются адреса из `.env`: PostgreSQL на
   `localhost:5432` и Redis на `localhost:6379`. Тестовые учётные данные можно
   переопределить через `INITIAL_ADMIN_EMAIL` и `INITIAL_ADMIN_PASSWORD`.

4. Примените миграции и создайте начального администратора:

   ```bash
   cd backend
   poetry run alembic upgrade head
   poetry run python -m app.seed
   ```

5. В отдельных терминалах из каталога `backend` запустите API и worker:

   ```bash
   poetry run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
   ```

   ```bash
   poetry run rq worker --url redis://localhost:6379/0 analysis
   ```

Каталоги загрузок, нормализованных файлов и результатов анализа по умолчанию находятся
в `data/uploads`, `data/normalized` и `data/runs` в корне репозитория. Один загружаемый
CSV, TSV или TXT-файл может иметь размер до 200 МиБ; за один запрос принимается не
более 10 файлов.

## Полный конвейер анализа

Запуск обрабатывает не одну опорную дату, а все доступные даты выбранного окна: последние
7 доступных дат для `week`, последние 30 для `month`, включительный интервал для `range`
и весь набор для `all`. Для каждой даты выполняются построение раздельных SIEM/PAN
признаков, Isolation Forest + LOF scoring, explainability и сохранение всех сущностей.
`top_n` и `top_pct` ограничивают только представление в UI/отчётах и не обрезают аналитику.

Поддерживаемые режимы параметра `mode`:

- `report` — scoring/explainability, графики и SOC-отчёт;
- `metrics` — scoring/explainability и proxy-метрики со stability grid;
- `report+metrics` и `full` — оба набора артефактов;
- `dry-run` — проверка входов, дат и конфигурации без обучения моделей.

В `data/runs/<run_id>` сохраняются единая обратимая карта пользователей, полные features
и score CSV, explainability, proxy metrics CSV/JSON, stability CSV/PNG, графические
PNG/CSV-отчёты, SOC Markdown/PDF/context CSV и каталог `meta` с `manifest.json`,
`run_config.json`, `requested_run.json`. Эти файлы содержат параметры модели,
preprocessing и версии библиотек, поэтому эксперимент можно повторить вне приложения.
По умолчанию stability grid рассчитывается для последней даты выбранного периода (как в
исходном экспериментальном скрипте); `stability_all_dates=true` включает перебор для
каждой даты ценой существенно большего времени выполнения.

## Проверки

Из каталога `backend`:

```bash
poetry run pytest
poetry run ruff check app tests
```

Если менялась схема базы, создайте миграцию и проверьте её применение:

```bash
poetry run alembic revision --autogenerate -m "описание изменения"
poetry run alembic upgrade head
```

Тестовые логин и пароль предназначены только для локальной разработки. Для общей или
production-среды обязательно задайте собственные `JWT_SECRET`,
`INITIAL_ADMIN_EMAIL` и `INITIAL_ADMIN_PASSWORD`.
