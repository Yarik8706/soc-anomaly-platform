"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { apiFetch, apiText } from "@/lib/api/client";
import type { ReportRead } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { ChevronLeft, Download, FileText } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export function ReportDetailView({ id }: { id: string }) {
  const [report, setReport] = useState<ReportRead | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const value = await apiFetch<ReportRead>(`/reports/${id}`);
      setReport(value);
      if (value.status === "completed") setContent(await apiText(`/reports/${id}/content`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Отчёт не найден");
    } finally {
      setLoading(false);
    }
  }, [id]);
  useEffect(() => {
    let active = true;
    Promise.all([apiFetch<ReportRead>(`/reports/${id}`)])
      .then(async ([value]) => {
        if (!active) return;
        setReport(value);
        if (value.status === "completed") {
          const text = await apiText(`/reports/${id}/content`);
          if (active) setContent(text);
        }
      })
      .catch(
        (caught: unknown) =>
          active && setError(caught instanceof Error ? caught.message : "Отчёт не найден"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);
  const pending = report && ["queued", "running"].includes(report.status);
  useEffect(() => {
    if (!pending) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const value = await apiFetch<ReportRead>(`/reports/${id}`);
        if (active) setReport(value);
      } catch {
        /* retry on next render */
      }
    }, 2500);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [id, pending, report]);
  useEffect(() => {
    if (report?.status !== "completed" || content !== null) return;
    let active = true;
    apiText(`/reports/${id}/content`)
      .then((value) => {
        if (active) setContent(value);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "Содержимое недоступно");
      });
    return () => {
      active = false;
    };
  }, [content, id, report?.status]);
  if (loading) return <LoadingState label="Загружаем отчёт" />;
  if (error || !report)
    return (
      <ErrorState
        message={error ?? "Отчёт не найден"}
        action={<Button onClick={load}>Повторить</Button>}
      />
    );
  return (
    <div className="page-stack">
      <Link className="back-link" href="/reports">
        <ChevronLeft />К отчётам
      </Link>
      <PageHeader
        title="SOC-отчёт"
        description={`Запуск ${report.run_id} · ${formatDate(report.created_at)}`}
        actions={<Badge tone={statusTone(report.status)}>{statusLabel(report.status)}</Badge>}
      />
      {report.error_message ? (
        <Card className="error-card">
          <strong>Генерация завершилась ошибкой</strong>
          <p>{report.error_message}</p>
        </Card>
      ) : null}
      {report.files.length ? (
        <Card className="detail-card">
          <div className="section-heading">
            <div>
              <p className="section-label">Файлы</p>
              <h2>Скачать результат</h2>
            </div>
          </div>
          <div className="report-files">
            {report.files.map((file) => (
              <a
                className="report-file"
                href={`/api/backend/reports/${report.id}/download/${file.format}`}
                key={file.format}
              >
                <FileText />
                <span>
                  <strong>{file.filename}</strong>
                  <small>
                    {file.format.toUpperCase()} · {formatBytes(file.size)}
                  </small>
                </span>
                <Download />
              </a>
            ))}
          </div>
        </Card>
      ) : null}
      {pending ? (
        <LoadingState label="Отчёт формируется — статус обновится автоматически" />
      ) : content ? (
        <Card className="markdown-card">
          <ReactMarkdown skipHtml>{content}</ReactMarkdown>
        </Card>
      ) : !report.error_message ? (
        <EmptyState
          title="Содержимое ещё не готово"
          description="Обновите страницу через несколько секунд."
        />
      ) : null}
    </div>
  );
}
