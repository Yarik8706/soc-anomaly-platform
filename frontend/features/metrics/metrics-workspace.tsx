"use client";

import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { apiFetch } from "@/lib/api/client";
import type { AnalysisRunRead, Histogram, ProxyMetricsRead, StabilitySlice } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { Activity, Gauge, GitCompareArrows } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { histogramPoints, metricValue } from "./histogram";

export function MetricsWorkspace({ selectedRun }: { selectedRun: string }) {
  const router = useRouter();
  const [runs, setRuns] = useState<AnalysisRunRead[]>([]);
  const [metrics, setMetrics] = useState<ProxyMetricsRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<AnalysisRunRead[]>("/runs"),
      selectedRun
        ? apiFetch<ProxyMetricsRead>(`/metrics/runs/${selectedRun}`)
        : Promise.resolve(null),
    ])
      .then(([runItems, metricData]) => {
        if (active) {
          setRuns(runItems);
          setMetrics(metricData);
        }
      })
      .catch(
        (caught: unknown) =>
          active && setError(caught instanceof Error ? caught.message : "Метрики недоступны"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [selectedRun]);
  const completed = useMemo(() => runs.filter((run) => run.status === "completed"), [runs]);
  const features = useMemo(
    () =>
      Object.entries(metrics?.contributing_features ?? {}).sort(
        (a, b) => Math.abs(b[1]) - Math.abs(a[1]),
      ),
    [metrics],
  );
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Model health"
        title="Метрики качества"
        description="Распределения score, стабильность топа и признаки, влияющие на модель."
        actions={
          <div className="metrics-run-select">
            <Select
              id="metrics-run"
              label="Завершённый запуск"
              value={selectedRun}
              onChange={(e) =>
                router.push(
                  e.target.value
                    ? `/metrics?run_id=${encodeURIComponent(e.target.value)}`
                    : "/metrics",
                )
              }
            >
              <option value="">Выберите запуск</option>
              {completed.map((run) => (
                <option value={run.id} key={run.id}>
                  {run.id.slice(0, 8)} · {formatDate(run.finished_at)}
                </option>
              ))}
            </Select>
          </div>
        }
      />
      {loading ? (
        <LoadingState label="Загружаем метрики" />
      ) : error ? (
        <ErrorState message={error} />
      ) : !selectedRun ? (
        <EmptyState
          title="Выберите запуск"
          description="Метрики доступны для завершённых запусков анализа."
        />
      ) : !metrics ? (
        <EmptyState
          title="Метрики не найдены"
          description="Для выбранного запуска данные ещё не рассчитаны."
        />
      ) : (
        <>
          <section className="metrics-grid">
            <HistogramChart title="Пользователи" histogram={metrics.score_distributions.user} />
            <HistogramChart title="Хосты" histogram={metrics.score_distributions.host} />
          </section>
          <section className="metrics-grid">
            <StabilityCard title="Стабильность пользователей" value={metrics.stability.user} />
            <StabilityCard title="Стабильность хостов" value={metrics.stability.host} />
          </section>
          <Card className="detail-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Explainability</p>
                <h2>Вклад признаков</h2>
              </div>
              <span className="muted">Рассчитано {formatDate(metrics.generated_at)}</span>
            </div>
            {features.length ? (
              <div className="feature-bars">
                {features.map(([name, value]) => (
                  <div key={name}>
                    <span>
                      <strong>{name}</strong>
                      <small>{value.toFixed(4)}</small>
                    </span>
                    <span>
                      <span
                        style={{
                          width: `${Math.max(3, (Math.abs(value) / Math.max(...features.map(([, item]) => Math.abs(item)), 0.0001)) * 100)}%`,
                        }}
                      />
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">Недостаточно данных о признаках.</p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function HistogramChart({ title, histogram }: { title: string; histogram: Histogram }) {
  const points = histogramPoints(histogram);
  return (
    <Card className="detail-card histogram-card">
      <div>
        <p className="eyebrow">Score distribution</p>
        <h2>{title}</h2>
      </div>
      {points.length ? (
        <>
          <div className="histogram" aria-hidden="true">
            {points.map((point) => (
              <span
                style={{ height: `${Math.max(2, point.height)}%` }}
                key={point.label}
                title={`${point.label}: ${point.count}`}
              />
            ))}
          </div>
          <div
            className="histogram-table"
            role="table"
            aria-label={`Распределение score: ${title}`}
          >
            {points.map((point) => (
              <div role="row" key={point.label}>
                <span role="cell">{point.label}</span>
                <strong role="cell">{point.count}</strong>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="muted">Недостаточно данных для распределения.</p>
      )}
    </Card>
  );
}

function StabilityCard({ title, value }: { title: string; value: StabilitySlice }) {
  return (
    <Card className="detail-card stability-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Top-K stability</p>
          <h2>{title}</h2>
        </div>
        <GitCompareArrows />
      </div>
      <div className="stability-values">
        <div>
          <Activity />
          <span>
            <small>Jaccard@K</small>
            <strong>{metricValue(value.jaccard_at_k)}</strong>
          </span>
        </div>
        <div>
          <Gauge />
          <span>
            <small>Overlap@K</small>
            <strong>{metricValue(value.overlap_at_k)}</strong>
          </span>
        </div>
        <div>
          <GitCompareArrows />
          <span>
            <small>Spearman@K</small>
            <strong>{metricValue(value.spearman_at_k)}</strong>
          </span>
        </div>
      </div>
      <p className="muted">
        Сравнение: {value.compared_run ? value.compared_run.slice(0, 8) : "предыдущего запуска нет"}
      </p>
    </Card>
  );
}
