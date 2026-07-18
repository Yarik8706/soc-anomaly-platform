"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useSession } from "@/features/auth/session-provider";
import { apiFetch } from "@/lib/api/client";
import type { AnalysisRunRead, ReportRead } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { FilePlus2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

export function ReportWorkspace() {
  const [runs, setRuns] = useState<AnalysisRunRead[]>([]);
  const [reports, setReports] = useState<ReportRead[]>([]);
  const [runId, setRunId] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const { canMutate } = useSession();
  useEffect(() => {
    let active = true;
    Promise.all([apiFetch<AnalysisRunRead[]>("/runs"), apiFetch<ReportRead[]>("/reports")])
      .then(([runItems, reportItems]) => {
        if (active) {
          setRuns(runItems);
          setReports(reportItems);
        }
      })
      .catch(
        (caught: unknown) =>
          active && setError(caught instanceof Error ? caught.message : "Ошибка загрузки"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);
  const hasActive = reports.some((item) => ["queued", "running"].includes(item.status));
  useEffect(() => {
    if (!hasActive) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const values = await apiFetch<ReportRead[]>("/reports");
        if (active) setReports(values);
      } catch {
        /* keep last stable snapshot */
      }
    }, 2500);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [hasActive, reports]);
  const completedRuns = useMemo(() => runs.filter((run) => run.status === "completed"), [runs]);

  async function createReport() {
    if (!runId) return;
    setCreating(true);
    try {
      const created = await apiFetch<ReportRead>(`/reports/runs/${runId}`, { method: "POST" });
      setReports((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      toast("Отчёт поставлен в очередь");
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : "Отчёт не создан", "error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="SOC-отчёты"
        description="Проверяемые сводки расследований в Markdown и PDF."
      />
      <Card className="report-create-card">
        <div>
          <p className="section-label">Новый отчёт</p>
          <h2>Сформировать по завершённому запуску</h2>
          <p>Генерация выполняется в фоне; статус обновится автоматически.</p>
        </div>
        <div className="report-create-controls">
          <Select
            id="report-run"
            label="Запуск"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
          >
            <option value="">Выберите запуск</option>
            {completedRuns.map((run) => (
              <option value={run.id} key={run.id}>
                {run.id.slice(0, 8)} · {formatDate(run.finished_at)}
              </option>
            ))}
          </Select>
          <Button
            disabled={!runId || !canMutate}
            loading={creating}
            icon={<FilePlus2 />}
            onClick={createReport}
          >
            Создать отчёт
          </Button>
        </div>
      </Card>
      <section className="section-stack">
        <div className="section-heading">
          <div>
            <p className="section-label">Архив</p>
            <h2>Все отчёты</h2>
          </div>
          <span className="muted">{reports.length} документов</span>
        </div>
        {loading ? (
          <LoadingState label="Загружаем отчёты" />
        ) : error ? (
          <ErrorState message={error} />
        ) : !reports.length ? (
          <EmptyState
            title="Отчётов пока нет"
            description="Выберите завершённый запуск и создайте первый отчёт."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <th>Отчёт</th>
                <th>Запуск</th>
                <th>Создан</th>
                <th>Статус</th>
                <th>Файлы</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.id}>
                  <td className="mono">{report.id.slice(0, 8)}</td>
                  <td className="mono">{report.run_id.slice(0, 8)}</td>
                  <td>{formatDate(report.created_at)}</td>
                  <td>
                    <Badge tone={statusTone(report.status)}>{statusLabel(report.status)}</Badge>
                  </td>
                  <td>
                    {report.files.map((file) => file.format.toUpperCase()).join(" · ") || "—"}
                  </td>
                  <td>
                    <Link className="table-link" href={`/reports/${report.id}`}>
                      Открыть
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </div>
  );
}
