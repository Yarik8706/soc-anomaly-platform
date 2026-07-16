# Frontend ↔ Backend contracts

Этот документ — рабочая спецификация для frontend SOC Anomaly Platform. Он позволяет
реализовывать интерфейс без чтения всего Python-кода. Источник истины — FastAPI-код в
`backend/app/api` и Pydantic-схемы в `backend/app/schemas` на момент коммита документа.

## 1. Общие правила интеграции

### Адреса

- В Docker Compose backend доступен frontend-контейнеру как `http://backend:8000`.
- С host-машины backend по умолчанию доступен как `http://localhost:8001`.
- У API нет общего префикса `/api` и нет настроенного CORS middleware.
- Swagger UI: `GET /docs`, OpenAPI JSON: `GET /openapi.json`.

Frontend использует same-origin BFF-прокси Next.js:

```text
Browser -> /api/backend/* -> Next.js server -> http://backend:8000/*
```

Это устраняет CORS-зависимость и позволяет хранить access token в `HttpOnly` cookie.
Клиентский код не должен читать или сохранять JWT в `localStorage`/`sessionStorage`.

### Авторизация

Все продуктовые endpoints, кроме `/health`, `/health/db` и `/auth/login`, требуют:

```http
Authorization: Bearer <access_token>
```

Access token живёт 30 минут по умолчанию. Refresh-token отсутствует. При `401` BFF
удаляет cookie сессии, а UI переводит пользователя на `/login` с сохранением безопасного
`returnTo`. При `403` сессия сохраняется, UI показывает отсутствие прав.

Роли:

| Роль | Чтение данных | Upload/run/report/status mutations | Users | Audit |
| --- | --- | --- | --- | --- |
| `admin` | да | да | чтение/создание/изменение | да |
| `analyst` | да | да | нет | нет |
| `viewer` | да | нет | нет | нет |

### Форматы и naming

- JSON-поля приходят в `snake_case`; frontend-модели сохраняют те же имена.
- UUID передаются строкой.
- `date` — `YYYY-MM-DD`.
- `datetime` — ISO 8601 строка; backend сейчас может отдавать значение без timezone suffix.
- Неизвестные значения enum UI должен показывать безопасным fallback, а не падать.
- Все списки, кроме anomalies/audit, возвращаются простым JSON-массивом без пагинации.

### Ошибки

Обычная ошибка FastAPI:

```json
{ "detail": "Human-readable message" }
```

Ошибка валидации запроса (`422`) имеет стандартный FastAPI-массив:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "field"],
      "msg": "Value error, ...",
      "input": null
    }
  ]
}
```

Особый случай `POST /uploads/{id}/normalize`: при невалидной структуре `detail` — объект
`FileValidationResult`, а не строка. Общий API client обязан поддерживать строку, объект
или массив и преобразовывать их в безопасное пользовательское сообщение.

Коды, которые должен различать UI:

| Код | Значение | Реакция frontend |
| ---: | --- | --- |
| 400 | некорректный файл/параметры | показать ошибку рядом с формой |
| 401 | нет/истекла сессия | очистить сессию и перейти на login |
| 403 | недостаточно роли | показать access denied, не разлогинивать |
| 404 | объект не найден | route-level not found или toast |
| 409 | конфликт состояния/дубликат | обновить данные и показать detail |
| 413 | файл больше 50 MiB | отклонить и на клиенте, показать лимит |
| 422 | schema/business validation | привязать к полям, если возможно |
| 503 | Redis/queue недоступна | оставить введённые данные, предложить retry |

## 2. Session BFF contract

Эти endpoints реализуются в Next.js и не существуют в FastAPI.

### `POST /api/session/login`

Request:

```json
{ "email": "admin@example.com", "password": "local-admin-change-me" }
```

BFF вызывает `POST /auth/login`, сохраняет `access_token` в cookie `soc_session`
(`HttpOnly`, `SameSite=Lax`, `Secure` вне local, `Path=/`, `Max-Age=expires_in`) и возвращает
только пользователя из `GET /auth/me`:

```json
{
  "id": "uuid",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-07-16T10:00:00"
}
```

### `GET /api/session`

Возвращает `UserRead`, если cookie валидна. При отсутствии/истечении — `401`.

### `DELETE /api/session`

Удаляет cookie локально. Backend logout/revocation endpoint отсутствует.

### `ANY /api/backend/{path}`

Проксирует method, query, body и безопасные headers в FastAPI. BFF добавляет bearer token,
не пересылает browser cookie в backend и пропускает `Content-Type`, `Content-Disposition`
и статус ответа. Для multipart нельзя вручную задавать boundary.

## 3. Health

### `GET /health`

Public, `200`:

```json
{ "status": "ok" }
```

### `GET /health/db`

Public, `200` при доступной БД:

```json
{ "status": "ok", "database": "connected" }
```

## 4. Auth and users

### Модели

```ts
type UserRole = "admin" | "analyst" | "viewer";

interface UserRead {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}
```

### `POST /auth/login`

Public. Password: 8–256 символов.

```json
{ "email": "admin@example.com", "password": "local-admin-change-me" }
```

`200`:

```json
{ "access_token": "jwt", "token_type": "bearer", "expires_in": 1800 }
```

Неверные credentials: `401 {"detail":"Invalid email or password"}`. UI всегда показывает
общую ошибку, не раскрывая существование email.

### `GET /auth/me`

Любая активная роль. Возвращает `UserRead`.

### `GET /users`

Только admin. Возвращает `UserRead[]`, новые сверху не гарантированы контрактом.

### `POST /users`

Только admin. Password: 12–256 символов.

```json
{
  "email": "analyst@example.com",
  "password": "strong-password",
  "role": "analyst"
}
```

`201 UserRead`; дублирующий email — `409`.

### `PATCH /users/{user_id}`

Только admin. Все поля опциональны; отправлять только изменённые.

```json
{ "role": "viewer", "is_active": false, "password": "new-strong-password" }
```

`200 UserRead`; неизвестный UUID — `404`.

## 5. Uploads

Ограничения: `.csv`, `.tsv`, `.txt`; максимум 50 MiB на файл; batch — 1–10 файлов.

### Модели

```ts
interface FileValidationResult {
  is_valid: boolean;
  encoding: "utf-8-sig" | "utf-8" | "cp1251" | null;
  delimiter: "\t" | "," | ";" | "|" | null;
  columns: string[];
  missing_critical_columns: string[];
  errors: string[];
  sampled_rows: number;
}

interface NormalizedArtifact {
  path: string;       // internal path; показывать basename, не делать ссылкой
  date: string;
  source: "SIEM" | "PAN";
  rows: number;
}

interface NormalizationResult {
  artifacts: NormalizedArtifact[];
  user_mapping_path: string; // internal path; не скачивается через текущий API
  processed_rows: number;
  skipped_rows: number;
  errors?: string[];
}

type UploadStatus = "pending" | "validated" | "invalid" | "normalized" | "failed";

interface UploadedFileRead {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  status: UploadStatus | string;
  uploaded_by: string | null;
  created_at: string;
  validation_result: FileValidationResult | null;
  validated_at: string | null;
  normalization_result: NormalizationResult | null;
  normalized_at: string | null;
}
```

### `GET /uploads`

Все роли. `200 UploadedFileRead[]`, сортировка `created_at desc`.

### `POST /uploads`

Admin/analyst. `multipart/form-data`, поле `file`. `201 UploadedFileRead`.

### `POST /uploads/batch`

Admin/analyst. `multipart/form-data`, повторяемое поле `files`. Batch атомарный: при ошибке
одного файла весь batch откатывается. `201 UploadedFileRead[]`.

### `GET /uploads/{file_id}`

Все роли. `200 UploadedFileRead`, неизвестный UUID — `404`.

### `POST /uploads/{file_id}/validate`

Admin/analyst. Body отсутствует. Обновляет `validation_result`, `validated_at`, `status`.

### `POST /uploads/{file_id}/normalize`

Admin/analyst. Body отсутствует. Backend повторно валидирует файл. Успех переводит status
в `normalized`; невалидный файл — `422` с `detail: FileValidationResult`; runtime failure —
`422` со строкой и status `failed`.

## 6. Analysis runs

### Модели и state machine

```ts
type AnalysisScope = "day" | "week" | "month" | "range" | "all";
type RunStatus = "pending" | "queued" | "running" | "completed" | "failed";

interface AnalysisRunRead {
  id: string;
  status: RunStatus | string;
  scope: AnalysisScope | string;
  target_date: string | null;
  start_date: string | null;
  end_date: string | null;
  parameters: Record<string, unknown> | null;
  upload_ids: string[] | null;
  stages: Record<string, { status?: string; [key: string]: unknown }> | null;
  artifacts: Record<string, unknown> | null;
  current_stage: string | null;
  job_id: string | null;
  attempts: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
```

Ожидаемый переход: `pending -> queued -> running -> completed|failed`. Polling нужен только
для `pending|queued|running`, интервал 2–5 секунд; запросы не должны накладываться.

### `POST /runs`

Admin/analyst. `upload_ids` обязателен и содержит минимум один UUID.

```json
{
  "scope": "day",
  "target_date": "2026-07-15",
  "start_date": null,
  "end_date": null,
  "parameters": { "n_estimators": 100, "top_n": 20 },
  "upload_ids": ["uuid-of-normalized-upload"]
}
```

Правила дат:

- `day|week|month`: обязателен `target_date`;
- `range`: обязательны `start_date`, `end_date`, причём start <= end;
- `all`: даты не нужны.

`201 AnalysisRunRead`, уже с status `queued`; очередь недоступна — `503`.

### `GET /runs`

Все роли. `200 AnalysisRunRead[]`, сортировка `created_at desc`. Фильтров в backend пока нет,
поэтому MVP фильтрует полученный список на клиенте.

### `GET /runs/{run_id}`

Все роли. `200 AnalysisRunRead`, неизвестный UUID — `404`.

### `POST /runs/{run_id}/retry`

Admin/analyst. Допустим только для `failed|completed`. Увеличивает `attempts`, очищает ошибку,
возвращает status `queued`. Иначе `409`; очередь недоступна — `503`.

## 7. Anomalies and investigation workflow

### Модели

```ts
type EntityType = "user" | "host";
type Severity = "critical" | "high" | "medium" | "low";
type AnomalyStatus = "new" | "investigating" | "incident" | "false_positive" | "closed";

interface AnomalyRead {
  id: string;
  run_id: string;
  entity_type: EntityType | string;
  entity: string;
  date: string;
  severity: Severity | string;
  score: number;
  rank: number;
  summary: string;
  status: AnomalyStatus | string;
  context: Record<string, unknown> | null;
  created_at: string;
}

interface AnomalyExplanationRead {
  feature_name: string;
  feature_value: number;
  baseline_value: number;
  contribution: number;
}

interface AnomalyActivityRead {
  id: string;
  actor_id: string | null;
  previous_status: string;
  new_status: string;
  comment: string | null;
  created_at: string;
}

interface AnomalyDetail extends AnomalyRead {
  explanations: AnomalyExplanationRead[];
  activities: AnomalyActivityRead[];
}
```

`context` может содержать массивы `ip_addresses`, `processes`, `events`, `users`,
`active_hours`; каждое поле опционально, дополнительные ключи допустимы.

### `GET /anomalies`

Все роли. Query:

| Параметр | Тип |
| --- | --- |
| `run_id` | UUID, optional |
| `date_from`, `date_to` | date, optional |
| `entity_type` | `user|host`, optional |
| `severity` | `critical|high|medium|low`, optional |
| `workflow_status` | `new|investigating|incident|false_positive|closed`, optional |
| `offset` | integer >= 0, default 0 |
| `limit` | 1..200, default 50 |

Response:

```ts
interface AnomalyList {
  items: AnomalyRead[];
  total: number;
  offset: number;
  limit: number;
  counters: Record<string, number>; // severity counters плюс total
}
```

Backend не принимает sort-параметр; текущая сортировка определяется сервисом.

### `GET /anomalies/{anomaly_id}`

Все роли. `200 AnomalyDetail`, неизвестный UUID — `404`.

### `PATCH /anomalies/{anomaly_id}/status`

Admin/analyst:

```json
{ "status": "incident", "comment": "Confirmed compromise" }
```

Комментарий до 2000 символов и обязателен для `incident`, `false_positive`, `closed`.
Успех: `200 AnomalyDetail` с обновлённой `activities`; конфликт перехода — `409`.

## 8. Reports

```ts
interface ReportFileRead {
  format: "markdown" | "pdf" | string;
  filename: string;
  size: number;
  url: string;
}

interface ReportRead {
  id: string;
  run_id: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  job_id: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  files: ReportFileRead[];
}
```

### `POST /reports/runs/{run_id}`

Admin/analyst. Только для completed run. `202 ReportRead` со status `queued`. Уже активный
отчёт или незавершённый run — `409`; очередь недоступна — `503`.

### `GET /reports?run_id={uuid}`

Все роли. `run_id` optional. `200 ReportRead[]`, сортировка `created_at desc`.

### `GET /reports/{report_id}`

Все роли. `200 ReportRead`. Polling нужен для `queued|running`.

### `GET /reports/{report_id}/content`

Все роли. `200 text/plain; charset=utf-8` с Markdown. Рендерить только через библиотеку с
отключённым raw HTML или выводить как plain text. Файла ещё нет — `404`.

### `GET /reports/{report_id}/download/{format_name}`

Все роли. `format_name`: `markdown|pdf`. Ответ — бинарный файл с `Content-Disposition`.
Скачивание выполнять через BFF, сохраняя этот header. Формат не готов — `404`.

## 9. Proxy metrics

### `GET /metrics/runs/{run_id}`

Все роли. Результат вычисляется/кэшируется backend при первом запросе.

```ts
interface Histogram {
  bin_edges: number[];
  counts: number[];
}

interface StabilitySlice {
  compared_run: string | null;
  jaccard_at_k: number | null;
  overlap_at_k: number | null;
  spearman_at_k: number | null;
}

interface ProxyMetricsRead {
  run_id: string;
  generated_at: string;
  score_distributions: { user: Histogram; host: Histogram };
  stability: { user: StabilitySlice; host: StabilitySlice };
  contributing_features: Record<string, number>;
}
```

Пустой набор даёт пустые `bin_edges/counts`; отсутствие предыдущего запуска даёт null во
всех stability metrics. UI должен показывать «Недостаточно данных», а не ноль.

## 10. Audit

Только admin.

```ts
interface AuditEventRead {
  id: string;
  user_id: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  severity: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

interface AuditEventList {
  items: AuditEventRead[];
  total: number;
  offset: number;
  limit: number;
}
```

### `GET /audit`

Query: `action`, `severity`, `object_type` (optional strings), `offset` >= 0, `limit` 1..500
(default 100). Backend не поддерживает фильтры по пользователю/периоду и отдельный detail
endpoint; для MVP доступные фильтры отправляются на сервер, остальные не имитируются как
полные серверные фильтры.

Известные actions: `auth.login`, `auth.login_failed`, `user.create`, `user.update`,
`upload.create`, `analysis.start`, `analysis.retry`, `anomaly.status_change`, `report.create`,
`report.export`.

## 11. UI state mapping

| Backend | UI label |
| --- | --- |
| `pending` | Ожидает постановки |
| `queued` | В очереди |
| `running` | Выполняется |
| `completed` | Завершено |
| `failed` | Ошибка |
| `new` | Новая |
| `investigating` | В проверке |
| `incident` | Инцидент |
| `false_positive` | Ложное срабатывание |
| `closed` | Закрыта |
| `critical` | Критическая |
| `high` | Высокая |
| `medium` | Средняя |
| `low` | Низкая |

Цвет не является единственным носителем смысла: status/severity всегда сопровождается
текстом и при необходимости иконкой.

## 12. Группы frontend-задач и коммитов

1. **Contracts** — этот документ.
2. **Foundation** — MYO-58, MYO-76, MYO-77, MYO-78: Next.js, BFF/API client, layout,
   UI primitives, типы, lint/type-check/tests.
3. **Data ingestion** — MYO-79, MYO-81: upload dropzone, batch upload, список и карточка,
   validate/normalize actions.
4. **Analysis runs** — MYO-80, MYO-82: форма, выбор normalized uploads, список, detail,
   polling и retry.
5. **Analyst workspace** — MYO-83, MYO-84, MYO-85: dashboard, server filters/pagination,
   detail, explanations/context, workflow history.
6. **Reporting & metrics** — MYO-86, MYO-87, MYO-88: report queue/polling/content/download,
   histograms, stability и contributing features.
7. **Security & operations** — MYO-89, MYO-90, MYO-91, MYO-92: HttpOnly session, RBAC,
   users, audit, production Docker and Compose.

Каждая группа завершается lint, type-check, tests и production build до отдельного commit.
