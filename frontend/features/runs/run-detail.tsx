"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { useSession } from "@/features/auth/session-provider";
import { apiFetch } from "@/lib/api/client";
import type { AnalysisRunRead } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { BarChart3, ChevronLeft, FileText, Radar, RefreshCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

const activeStatuses = new Set(["pending", "queued", "running"]);

export function RunDetail({ id }: { id: string }) {
  const [run, setRun] = useState<AnalysisRunRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const toast = useToast();
  const { canMutate } = useSession();
  const load = useCallback(async () => {
    try {
      const item = await apiFetch<AnalysisRunRead>(`/runs/${id}`);
      setRun(item);
      setError(null);
      return item;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Запуск не найден");
      return null;
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const item = await apiFetch<AnalysisRunRead>(`/runs/${id}`);
        if (!active) return;
        setRun(item);
        setError(null);
        setLoading(false);
        if (activeStatuses.has(item.status)) timer = setTimeout(poll, 3000);
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Запуск не найден");
          setLoading(false);
        }
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  const stages = useMemo(() => Object.entries(run?.stages ?? {}), [run?.stages]);
  const completed = stages.filter(([, value]) => value.status === "completed").length;
  const progress = stages.length ? Math.round((completed / stages.length) * 100) : 0;
  async function retry() {
    setRetrying(true);
    try {
      setRun(await apiFetch<AnalysisRunRead>(`/runs/${id}/retry`, { method: "POST" }));
      toast("Запуск повторно поставлен в очередь");
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : "Повтор не выполнен", "error");
    } finally {
      setRetrying(false);
    }
  }

  if (loading) return <LoadingState label="Загружаем состояние анализа" />;
  if (error || !run)
    return (
      <ErrorState
        message={error ?? "Запуск не найден"}
        action={<Button onClick={load}>Повторить</Button>}
      />
    );
  return (
    <div className="page-stack">
      <Link className="back-link" href="/runs">
        <ChevronLeft />К запускам
      </Link>
      <PageHeader
        title={`Анализ ${id.slice(0, 8)}`}
        description={`${statusLabel(run.scope)} · создан ${formatDate(run.created_at)}`}
        actions={
          run.status === "failed" || run.status === "completed" ? (
            <Button
              disabled={!canMutate}
              variant="secondary"
              loading={retrying}
              icon={<RefreshCcw />}
              onClick={retry}
            >
              Запустить повторно
            </Button>
          ) : undefined
        }
      />
      <section className="run-overview">
        <Card className="detail-card">
          <div className="section-heading">
            <p className="section-label">Состояние</p>
            <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
          </div>
          <div className="run-progress">
            <strong>{progress}%</strong>
            <span>
              <span style={{ width: `${progress}%` }} />
            </span>
            <small>
              {completed} из {stages.length} этапов завершено
            </small>
          </div>
          <dl className="definition-list">
            <div>
              <dt>Текущий этап</dt>
              <dd>{run.current_stage ? statusLabel(run.current_stage) : "—"}</dd>
            </div>
            <div>
              <dt>Попытка</dt>
              <dd>{run.attempts}</dd>
            </div>
            <div>
              <dt>Начат</dt>
              <dd>{formatDate(run.started_at)}</dd>
            </div>
            <div>
              <dt>Завершён</dt>
              <dd>{formatDate(run.finished_at)}</dd>
            </div>
          </dl>
        </Card>
        <Card className="detail-card">
          <p className="section-label">Этапы обработки</p>
          <div className="stage-list">
            {stages.map(([name, value], index) => (
              <div
                className={
                  name === run.current_stage ? "stage-item stage-item--active" : "stage-item"
                }
                key={name}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{statusLabel(name)}</strong>
                  <small>{statusLabel(value.status ?? "pending")}</small>
                </div>
                <Badge tone={statusTone(value.status ?? "pending")}>
                  {statusLabel(value.status ?? "pending")}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      </section>
      {run.error_message ? (
        <Card className="error-card">
          <strong>Причина ошибки</strong>
          <p>{run.error_message}</p>
        </Card>
      ) : null}
      <Card className="detail-card">
        <div className="section-heading">
          <div>
            <p className="section-label">Связанные данные</p>
            <h2>Данные и результаты</h2>
          </div>
        </div>
        <div className="link-grid">
          <div>
            <FileText />
            <strong>Входные файлы</strong>
            <span>{run.upload_ids?.length ?? 0}</span>
            <div>
              {run.upload_ids?.map((uploadId) => (
                <Link key={uploadId} href={`/uploads/${uploadId}`}>
                  {uploadId.slice(0, 8)}…
                </Link>
              ))}
            </div>
          </div>
          <Link href={`/anomalies?run_id=${run.id}`}>
            <Radar />
            <strong>Аномалии</strong>
            <small>Открыть результаты</small>
          </Link>
          <Link href={`/metrics?run_id=${run.id}`}>
            <BarChart3 />
            <strong>Метрики</strong>
            <small>Качество модели</small>
          </Link>
          <Link href={`/reports?run_id=${run.id}`}>
            <FileText />
            <strong>Отчёты</strong>
            <small>Создать SOC-сводку</small>
          </Link>
        </div>
      </Card>
    </div>
  );
}
