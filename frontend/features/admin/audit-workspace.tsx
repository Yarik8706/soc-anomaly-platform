"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table } from "@/components/ui/table";
import { apiFetch, toQuery } from "@/lib/api/client";
import type { AuditEventList, AuditEventRead } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { statusTone } from "@/lib/status";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";

interface AuditFilters {
  action: string;
  severity: string;
  object_type: string;
  offset: number;
  limit: number;
}
const initial: AuditFilters = { action: "", severity: "", object_type: "", offset: 0, limit: 50 };

export function AuditWorkspace() {
  const [filters, setFilters] = useState(initial);
  const [draft, setDraft] = useState(initial);
  const [data, setData] = useState<AuditEventList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditEventRead | null>(null);
  useEffect(() => {
    let active = true;
    apiFetch<AuditEventList>(
      `/audit${toQuery({ action: filters.action, severity: filters.severity, object_type: filters.object_type, offset: filters.offset, limit: filters.limit })}`,
    )
      .then((value) => active && setData(value))
      .catch(
        (caught: unknown) =>
          active && setError(caught instanceof Error ? caught.message : "Аудит недоступен"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [filters]);
  function apply(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setFilters({ ...draft, offset: 0 });
  }
  function paginate(offset: number) {
    setLoading(true);
    setFilters({ ...filters, offset });
  }
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Security operations"
        title="Журнал аудита"
        description="Неизменяемая последовательность значимых действий и событий безопасности."
      />
      <Card className="filter-card">
        <form className="audit-filter-grid" onSubmit={apply}>
          <Input
            id="audit-action"
            label="Действие"
            placeholder="anomaly.status_change"
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
          />
          <Input
            id="audit-object"
            label="Тип объекта"
            placeholder="anomaly"
            value={draft.object_type}
            onChange={(e) => setDraft({ ...draft, object_type: e.target.value })}
          />
          <Select
            id="audit-severity"
            label="Важность"
            value={draft.severity}
            onChange={(e) => setDraft({ ...draft, severity: e.target.value })}
          >
            <option value="">Все</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </Select>
          <Button type="submit" icon={<Search />}>
            Найти
          </Button>
        </form>
      </Card>
      {loading ? (
        <LoadingState label="Загружаем аудит" />
      ) : error ? (
        <ErrorState message={error} />
      ) : !data?.items.length ? (
        <EmptyState
          title="Событий не найдено"
          description="Измените фильтры или дождитесь новых событий."
        />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <th>Время</th>
                <th>Действие</th>
                <th>Объект</th>
                <th>Важность</th>
                <th>Пользователь</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((event) => (
                <tr key={event.id}>
                  <td>{formatDate(event.created_at)}</td>
                  <td className="mono">{event.action}</td>
                  <td>
                    {event.object_type}
                    <small className="table-subline mono">{event.object_id ?? "—"}</small>
                  </td>
                  <td>
                    <Badge tone={statusTone(event.severity)}>{event.severity}</Badge>
                  </td>
                  <td className="mono">{event.user_id?.slice(0, 8) ?? "system"}</td>
                  <td>
                    <Button variant="ghost" onClick={() => setSelected(event)}>
                      Детали
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="pagination">
            <span>
              Показаны {data.offset + 1}–{Math.min(data.offset + data.limit, data.total)} из{" "}
              {data.total}
            </span>
            <div>
              <Button
                variant="secondary"
                disabled={data.offset === 0}
                onClick={() => paginate(Math.max(0, data.offset - data.limit))}
              >
                Назад
              </Button>
              <Button
                variant="secondary"
                disabled={data.offset + data.limit >= data.total}
                onClick={() => paginate(data.offset + data.limit)}
              >
                Дальше
              </Button>
            </div>
          </div>
        </>
      )}
      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title="Детали события"
        description={selected ? formatDate(selected.created_at) : undefined}
      >
        <div className="modal-body">
          {selected ? (
            <>
              <dl className="definition-list">
                <div>
                  <dt>ID</dt>
                  <dd className="mono">{selected.id}</dd>
                </div>
                <div>
                  <dt>Действие</dt>
                  <dd>{selected.action}</dd>
                </div>
                <div>
                  <dt>Объект</dt>
                  <dd>
                    {selected.object_type} · {selected.object_id ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt>Пользователь</dt>
                  <dd className="mono">{selected.user_id ?? "system"}</dd>
                </div>
              </dl>
              <div>
                <p className="eyebrow">Payload</p>
                <pre className="audit-json">{JSON.stringify(selected.details ?? {}, null, 2)}</pre>
              </div>
            </>
          ) : null}
        </div>
      </Modal>
    </div>
  );
}
