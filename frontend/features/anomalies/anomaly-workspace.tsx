"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableToolbar } from "@/components/ui/table";
import { apiFetch, toQuery } from "@/lib/api/client";
import type { AnomalyList, AnomalyRead } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { Activity, CircleAlert, ShieldAlert, Telescope } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { anomalyFilterQuery, type AnomalyFilters } from "./query";

export function AnomalyWorkspace({ initialFilters }: { initialFilters: AnomalyFilters }) {
  const router = useRouter();
  const [draft, setDraft] = useState(initialFilters);
  const [data, setData] = useState<AnomalyList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const query = anomalyFilterQuery(initialFilters);

  useEffect(() => {
    let active = true;
    apiFetch<AnomalyList>(
      `/anomalies${toQuery({
        run_id: initialFilters.run_id,
        date_from: initialFilters.date_from,
        date_to: initialFilters.date_to,
        entity_type: initialFilters.entity_type,
        severity: initialFilters.severity,
        workflow_status: initialFilters.workflow_status,
        offset: initialFilters.offset,
        limit: initialFilters.limit,
      })}`,
    )
      .then((result) => active && setData(result))
      .catch(
        (caught: unknown) =>
          active && setError(caught instanceof Error ? caught.message : "Ошибка загрузки"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [initialFilters]);

  const items = useMemo(
    () => sortAnomalies(data?.items ?? [], initialFilters.sort),
    [data, initialFilters.sort],
  );
  function navigate(next: AnomalyFilters) {
    const nextQuery = anomalyFilterQuery(next);
    router.push(`/anomalies${nextQuery ? `?${nextQuery}` : ""}`);
  }
  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    navigate({ ...draft, offset: 0 });
  }
  const counters = data?.counters ?? {};

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Analyst workspace"
        title="Аномалии"
        description="Приоритизированные сигналы по пользователям и хостам с проверяемым workflow."
      />
      <section className="metric-grid anomaly-counters" aria-label="Сводка аномалий">
        <Counter icon={<Activity />} label="Всего" value={data?.total ?? 0} />
        <Counter icon={<ShieldAlert />} label="Критические" value={counters.critical ?? 0} />
        <Counter icon={<Telescope />} label="В проверке" value={counters.investigating ?? 0} />
        <Counter icon={<CircleAlert />} label="Инциденты" value={counters.incident ?? 0} />
      </section>
      <Card className="filter-card">
        <form className="anomaly-filter-grid" onSubmit={applyFilters}>
          <Input
            id="run-filter"
            label="Run ID"
            value={draft.run_id}
            onChange={(e) => setDraft({ ...draft, run_id: e.target.value })}
          />
          <Input
            id="date-from"
            label="Дата от"
            type="date"
            value={draft.date_from}
            onChange={(e) => setDraft({ ...draft, date_from: e.target.value })}
          />
          <Input
            id="date-to"
            label="Дата до"
            type="date"
            value={draft.date_to}
            onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
          />
          <Select
            id="entity-filter"
            label="Сущность"
            value={draft.entity_type}
            onChange={(e) =>
              setDraft({ ...draft, entity_type: e.target.value as AnomalyFilters["entity_type"] })
            }
          >
            <option value="">Все</option>
            <option value="user">Пользователь</option>
            <option value="host">Хост</option>
          </Select>
          <Select
            id="severity-filter"
            label="Критичность"
            value={draft.severity}
            onChange={(e) =>
              setDraft({ ...draft, severity: e.target.value as AnomalyFilters["severity"] })
            }
          >
            <option value="">Все</option>
            <option value="critical">Критическая</option>
            <option value="high">Высокая</option>
            <option value="medium">Средняя</option>
            <option value="low">Низкая</option>
          </Select>
          <Select
            id="workflow-filter"
            label="Статус"
            value={draft.workflow_status}
            onChange={(e) =>
              setDraft({
                ...draft,
                workflow_status: e.target.value as AnomalyFilters["workflow_status"],
              })
            }
          >
            <option value="">Все</option>
            <option value="new">Новая</option>
            <option value="investigating">В проверке</option>
            <option value="incident">Инцидент</option>
            <option value="false_positive">Ложное срабатывание</option>
            <option value="closed">Закрыта</option>
          </Select>
          <Button type="submit">Применить</Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              navigate({
                ...initialFilters,
                run_id: "",
                date_from: "",
                date_to: "",
                entity_type: "",
                severity: "",
                workflow_status: "",
                offset: 0,
              })
            }
          >
            Сбросить
          </Button>
        </form>
      </Card>
      <section className="section-stack">
        <TableToolbar>
          <div>
            <p className="eyebrow">Очередь разбора</p>
            <h2>{data ? `${data.total} сигналов` : "Сигналы"}</h2>
          </div>
          <div className="filter-row">
            <Select
              id="sort-anomalies"
              label="Сортировка страницы"
              value={initialFilters.sort}
              onChange={(e) =>
                navigate({
                  ...initialFilters,
                  sort: e.target.value as AnomalyFilters["sort"],
                  offset: 0,
                })
              }
            >
              <option value="rank">По рангу</option>
              <option value="score_desc">Score: убывание</option>
              <option value="score_asc">Score: возрастание</option>
              <option value="date_desc">Сначала новые</option>
            </Select>
            <Select
              id="page-size"
              label="На странице"
              value={initialFilters.limit}
              onChange={(e) =>
                navigate({ ...initialFilters, limit: Number(e.target.value), offset: 0 })
              }
            >
              <option value="20">20</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </Select>
          </div>
        </TableToolbar>
        {loading ? (
          <LoadingState label="Загружаем аномалии" />
        ) : error ? (
          <ErrorState
            message={error}
            action={<Button onClick={() => router.refresh()}>Повторить</Button>}
          />
        ) : !items.length ? (
          <EmptyState
            title="Аномалий не найдено"
            description="Измените фильтры или дождитесь завершения анализа."
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <th>Ранг</th>
                  <th>Сущность</th>
                  <th>Дата</th>
                  <th>Критичность</th>
                  <th>Score</th>
                  <th>Workflow</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="mono">#{item.rank}</td>
                    <td>
                      <strong>{item.entity}</strong>
                      <small className="table-subline">{item.entity_type}</small>
                    </td>
                    <td>{formatDate(item.date)}</td>
                    <td>
                      <Badge tone={statusTone(item.severity)}>{statusLabel(item.severity)}</Badge>
                    </td>
                    <td className="score-cell">{item.score.toFixed(4)}</td>
                    <td>
                      <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                    </td>
                    <td>
                      <Link
                        className="table-link"
                        href={`/anomalies/${item.id}?back=${encodeURIComponent(query)}`}
                      >
                        Разобрать
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="pagination">
              <span>
                Показаны {initialFilters.offset + 1}–
                {Math.min(initialFilters.offset + initialFilters.limit, data?.total ?? 0)} из{" "}
                {data?.total ?? 0}
              </span>
              <div>
                <Button
                  variant="secondary"
                  disabled={initialFilters.offset === 0}
                  onClick={() =>
                    navigate({
                      ...initialFilters,
                      offset: Math.max(0, initialFilters.offset - initialFilters.limit),
                    })
                  }
                >
                  Назад
                </Button>
                <Button
                  variant="secondary"
                  disabled={initialFilters.offset + initialFilters.limit >= (data?.total ?? 0)}
                  onClick={() =>
                    navigate({
                      ...initialFilters,
                      offset: initialFilters.offset + initialFilters.limit,
                    })
                  }
                >
                  Дальше
                </Button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function Counter({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <Card className="metric-card">
      <span className="metric-icon">{icon}</span>
      <p>{label}</p>
      <strong>{value}</strong>
    </Card>
  );
}

function sortAnomalies(items: AnomalyRead[], sort: AnomalyFilters["sort"]): AnomalyRead[] {
  return [...items].sort((a, b) =>
    sort === "score_desc"
      ? b.score - a.score
      : sort === "score_asc"
        ? a.score - b.score
        : sort === "date_desc"
          ? Date.parse(b.date) - Date.parse(a.date)
          : a.rank - b.rank,
  );
}
