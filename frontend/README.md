# SOC Lens frontend

Next.js frontend для SOC Anomaly Platform. Контракты API описаны в
[`../docs/frontend-backend-contracts.md`](../docs/frontend-backend-contracts.md).

## Локальная разработка

```bash
npm install
cp .env.example .env.local
npm run dev
```

По умолчанию приложение открывается на <http://localhost:3000>, а BFF-прокси обращается
к backend на `http://localhost:8001`. Для Docker используется
`BACKEND_INTERNAL_URL=http://backend:8000`.

## Проверки

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Новые backend endpoints сначала добавляются в `lib/api/types.ts`, затем вызываются через
`apiFetch` из `lib/api/client.ts`. UI не обращается к FastAPI напрямую.
