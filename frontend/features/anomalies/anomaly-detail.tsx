"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { useSession } from "@/features/auth/session-provider";
import { apiFetch } from "@/lib/api/client";
import type { AnomalyDetail, AnomalyStatus } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { ChevronLeft, Clock3, Save, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { statusCommentError } from "./query";

const workflowStatuses: AnomalyStatus[] = [
  "new",
  "investigating",
  "incident",
  "false_positive",
  "closed",
];

export function AnomalyDetailView({ id, back }: { id: string; back?: string }) {
  const [anomaly, setAnomaly] = useState<AnomalyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<AnomalyStatus>("new");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const toast = useToast();
  const { canMutate } = useSession();
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const value = await apiFetch<AnomalyDetail>(`/anomalies/${id}`);
      setAnomaly(value);
      setStatus(value.status as AnomalyStatus);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Аномалия не найдена");
    } finally {
      setLoading(false);
    }
  }, [id]);
  useEffect(() => {
    let active = true;
    apiFetch<AnomalyDetail>(`/anomalies/${id}`)
      .then((value) => {
        if (active) {
          setAnomaly(value);
          setStatus(value.status as AnomalyStatus);
        }
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "Аномалия не найдена");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);
  const maxContribution = useMemo(
    () =>
      Math.max(
        ...(anomaly?.explanations.map((item) => Math.abs(item.contribution)) ?? [1]),
        0.0001,
      ),
    [anomaly],
  );

  async function saveWorkflow(event: React.FormEvent) {
    event.preventDefault();
    const validation = statusCommentError(status, comment);
    setFormError(validation);
    if (validation) return;
    setSaving(true);
    try {
      const updated = await apiFetch<AnomalyDetail>(`/anomalies/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, comment: comment.trim() || null }),
      });
      setAnomaly(updated);
      setComment("");
      toast("Статус и журнал обновлены");
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : "Статус не обновлён", "error");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingState label="Загружаем сигнал" />;
  if (error || !anomaly)
    return (
      <ErrorState
        message={error ?? "Аномалия не найдена"}
        action={<Button onClick={load}>Повторить</Button>}
      />
    );
  const safeBack = back ? `/anomalies?${back.replace(/^\?/, "")}` : "/anomalies";
  return (
    <div className="page-stack">
      <Link className="back-link" href={safeBack}>
        <ChevronLeft />К очереди разбора
      </Link>
      <PageHeader
        title={anomaly.entity}
        description={anomaly.summary}
        actions={
          <>
            <Badge tone={statusTone(anomaly.severity)}>{statusLabel(anomaly.severity)}</Badge>
            <Badge tone={statusTone(anomaly.status)}>{statusLabel(anomaly.status)}</Badge>
          </>
        }
      />
      <section className="anomaly-detail-grid">
        <Card className="detail-card">
          <p className="section-label">Сигнал</p>
          <div className="anomaly-score">
            <ShieldAlert />
            <span>
              <strong>{anomaly.score.toFixed(4)}</strong>
              <small>anomaly score</small>
            </span>
          </div>
          <dl className="definition-list">
            <div>
              <dt>Дата</dt>
              <dd>{formatDate(anomaly.date)}</dd>
            </div>
            <div>
              <dt>Isolation Forest</dt>
              <dd>
                {formatScore(anomaly.score_isolation_forest)} · norm{" "}
                {formatScore(anomaly.score_isolation_forest_norm)} · rank #{anomaly.rank_isolation_forest ?? "—"}
              </dd>
            </div>
            <div>
              <dt>LOF</dt>
              <dd>
                {formatScore(anomaly.score_lof)} · norm {formatScore(anomaly.score_lof_norm)} ·
                rank #{anomaly.rank_lof ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Run ID</dt>
              <dd className="mono">{anomaly.run_id}</dd>
            </div>
            <div>
              <dt>Anomaly ID</dt>
              <dd className="mono">{anomaly.id}</dd>
            </div>
            <div>
              <dt>Создана</dt>
              <dd>{formatDate(anomaly.created_at)}</dd>
            </div>
          </dl>
        </Card>
        <Card className="detail-card detail-card--wide">
          <div className="section-heading">
            <div>
              <p className="section-label">Объяснимость</p>
              <h2>Почему это аномалия</h2>
            </div>
            <span className="muted">Вклад относительно baseline</span>
          </div>
          {anomaly.explanations.length ? (
            <div className="explanation-list">
              {anomaly.explanations.map((item) => (
                <div className="explanation-row" key={item.feature_name}>
                  <div>
                    <strong>{item.feature_name}</strong>
                    <small>
                      {item.feature_value.toFixed(3)} vs {item.baseline_value.toFixed(3)}
                    </small>
                  </div>
                  <span>
                    <span
                      style={{
                        width: `${Math.max(4, (Math.abs(item.contribution) / maxContribution) * 100)}%`,
                      }}
                    />
                  </span>
                  <strong className={item.contribution < 0 ? "negative" : ""}>
                    {item.contribution > 0 ? "+" : ""}
                    {item.contribution.toFixed(4)}
                  </strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Объяснения для этого сигнала не сформированы.</p>
          )}
        </Card>
      </section>
      <section className="anomaly-detail-grid">
        <Card className="detail-card">
          <p className="section-label">Контекст</p>
          {anomaly.context && Object.keys(anomaly.context).length ? (
            <dl className="definition-list">
              {Object.entries(anomaly.context).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{renderContext(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">Дополнительного контекста нет.</p>
          )}
        </Card>
        <Card className="detail-card detail-card--wide">
          <div className="section-heading">
            <div>
              <p className="section-label">Работа с инцидентом</p>
              <h2>Решение аналитика</h2>
            </div>
          </div>
          <form className="workflow-form" onSubmit={saveWorkflow}>
            <Select
              id="anomaly-status"
              label="Новый статус"
              value={status}
              disabled={!canMutate}
              onChange={(e) => {
                setStatus(e.target.value as AnomalyStatus);
                setFormError(null);
              }}
            >
              {workflowStatuses.map((item) => (
                <option value={item} key={item}>
                  {statusLabel(item)}
                </option>
              ))}
            </Select>
            <div className="field">
              <label htmlFor="workflow-comment">Комментарий</label>
              <textarea
                id="workflow-comment"
                className="control"
                disabled={!canMutate}
                value={comment}
                aria-invalid={Boolean(formError)}
                aria-describedby={formError ? "workflow-error" : undefined}
                onChange={(e) => {
                  setComment(e.target.value);
                  setFormError(null);
                }}
                placeholder="Наблюдения, основание решения или следующий шаг"
              />
              {formError ? (
                <p className="field-error" id="workflow-error">
                  {formError}
                </p>
              ) : (
                <p className="field-hint">
                  Обязателен для инцидента, ложного срабатывания и закрытия.
                </p>
              )}
            </div>
            <Button type="submit" loading={saving} disabled={!canMutate} icon={<Save />}>
              Сохранить решение
            </Button>
          </form>
        </Card>
      </section>
      <Card className="detail-card">
        <div className="section-heading">
          <div>
            <p className="section-label">История действий</p>
            <h2>История действий</h2>
          </div>
        </div>
        {anomaly.activities.length ? (
          <ol className="activity-timeline">
            {anomaly.activities.map((item) => (
              <li key={item.id}>
                <Clock3 />
                <div>
                  <strong>
                    {statusLabel(item.previous_status)} → {statusLabel(item.new_status)}
                  </strong>
                  <p>{item.comment || "Без комментария"}</p>
                  <small>
                    {formatDate(item.created_at)} · {item.actor_id ?? "system"}
                  </small>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">Изменений статуса ещё не было.</p>
        )}
      </Card>
    </div>
  );
}

function renderContext(value: unknown): React.ReactNode {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    return String(value);
  return <code className="context-value">{JSON.stringify(value)}</code>;
}

function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(4);
}
