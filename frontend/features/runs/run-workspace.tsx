"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useSession } from "@/features/auth/session-provider";
import { apiFetch } from "@/lib/api/client";
import type { AnalysisRunRead, AnalysisScope, UploadedFileRead } from "@/lib/api/types";
import { formatDate, shortId } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { Play, Plus, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { validateRun, type RunFormValues } from "./run-validation";

const initialForm: RunFormValues = {
  scope: "day",
  targetDate: "",
  startDate: "",
  endDate: "",
  uploadIds: [],
  mode: "full",
  nEstimators: 100,
  topN: 20,
  contamination: 0.05,
  nNeighbors: 20,
  randomState: 42,
  maxSamples: "auto",
  topFeatures: 5,
  topPct: 0.05,
};

export function RunWorkspace() {
  const [runs, setRuns] = useState<AnalysisRunRead[]>([]);
  const [uploads, setUploads] = useState<UploadedFileRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState("");
  const [scopeFilter, setScopeFilter] = useState("");
  const router = useRouter();
  const toast = useToast();
  const { canMutate } = useSession();

  useEffect(() => {
    let active = true;
    Promise.all([apiFetch<AnalysisRunRead[]>("/runs"), apiFetch<UploadedFileRead[]>("/uploads")])
      .then(([runItems, uploadItems]) => {
        if (active) {
          setRuns(runItems);
          setUploads(uploadItems.filter(({ status }) => status === "normalized"));
        }
      })
      .catch((caught: unknown) => {
        if (active)
          setError(caught instanceof Error ? caught.message : "Не удалось получить запуски");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredRuns = useMemo(
    () =>
      runs.filter(
        (run) =>
          (!statusFilter || run.status === statusFilter) &&
          (!scopeFilter || run.scope === scopeFilter),
      ),
    [runs, scopeFilter, statusFilter],
  );
  function update<K extends keyof RunFormValues>(key: K, value: RunFormValues[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: "" }));
  }
  function toggleUpload(id: string) {
    update(
      "uploadIds",
      form.uploadIds.includes(id)
        ? form.uploadIds.filter((item) => item !== id)
        : [...form.uploadIds, id],
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const nextErrors = validateRun(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setSubmitting(true);
    try {
      const payload = {
        scope: form.scope,
        target_date: form.targetDate || null,
        start_date: form.startDate || null,
        end_date: form.endDate || null,
        parameters: {
          mode: form.mode,
          n_estimators: form.nEstimators,
          top_n: form.topN,
          contamination: form.contamination,
          n_neighbors: form.nNeighbors,
          random_state: form.randomState,
          max_samples:
            form.maxSamples.trim().toLowerCase() === "auto"
              ? "auto"
              : Number(form.maxSamples),
          top_features: form.topFeatures,
          top_pct: form.topPct,
        },
        upload_ids: form.uploadIds,
      };
      const created = await apiFetch<AnalysisRunRead>("/runs", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast("Анализ поставлен в очередь");
      router.push(`/runs/${created.id}`);
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : "Не удалось создать запуск", "error");
      setSubmitting(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Запуски анализа"
        description="Создавайте ML-анализ и следите за выполнением каждого этапа."
        actions={
          <Button
            disabled={!canMutate}
            icon={<Plus />}
            onClick={() => setShowForm((value) => !value)}
          >
            {showForm ? "Скрыть форму" : "Новый запуск"}
          </Button>
        }
      />
      {showForm ? (
        <Card className="run-form-card">
          <form onSubmit={submit}>
            <div className="section-heading">
              <div>
                <p className="section-label">Новый анализ</p>
                <h2>Параметры запуска</h2>
              </div>
              <Badge tone="running">Проверка перед запуском</Badge>
            </div>
            <div className="form-grid">
              <Select
                id="run-mode"
                label="Режим"
                value={form.mode}
                onChange={(event) => update("mode", event.target.value as RunFormValues["mode"])}
              >
                <option value="full">Полный конвейер</option>
                <option value="report+metrics">Отчёт и метрики</option>
                <option value="report">Только отчётность</option>
                <option value="metrics">Только метрики</option>
                <option value="dry-run">Проверка без анализа</option>
              </Select>
              <Select
                id="run-scope"
                label="Период"
                value={form.scope}
                onChange={(event) => update("scope", event.target.value as AnalysisScope)}
              >
                <option value="day">День</option>
                <option value="week">Неделя</option>
                <option value="month">Месяц</option>
                <option value="range">Диапазон</option>
                <option value="all">Все данные</option>
              </Select>
              {["day", "week", "month"].includes(form.scope) ? (
                <Input
                  id="target-date"
                  label="Опорная дата"
                  type="date"
                  value={form.targetDate}
                  error={errors.targetDate}
                  onChange={(event) => update("targetDate", event.target.value)}
                />
              ) : null}
              {form.scope === "range" ? (
                <>
                  <Input
                    id="start-date"
                    label="Начало"
                    type="date"
                    value={form.startDate}
                    error={errors.startDate}
                    onChange={(event) => update("startDate", event.target.value)}
                  />
                  <Input
                    id="end-date"
                    label="Конец"
                    type="date"
                    value={form.endDate}
                    error={errors.endDate}
                    onChange={(event) => update("endDate", event.target.value)}
                  />
                </>
              ) : null}
              <Input
                id="contamination"
                label="Contamination"
                type="number"
                min={0.001}
                max={0.5}
                step={0.001}
                value={form.contamination}
                error={errors.contamination}
                onChange={(event) => update("contamination", Number(event.target.value))}
              />
              <Input
                id="n-estimators"
                label="Количество деревьев"
                type="number"
                min={10}
                max={1000}
                value={form.nEstimators}
                error={errors.nEstimators}
                onChange={(event) => update("nEstimators", Number(event.target.value))}
              />
              <Input
                id="n-neighbors"
                label="Соседей LOF"
                type="number"
                min={1}
                max={10000}
                value={form.nNeighbors}
                error={errors.nNeighbors}
                onChange={(event) => update("nNeighbors", Number(event.target.value))}
              />
              <Input
                id="random-state"
                label="Random state"
                type="number"
                value={form.randomState}
                error={errors.randomState}
                onChange={(event) => update("randomState", Number(event.target.value))}
              />
              <Input
                id="max-samples"
                label="Max samples"
                value={form.maxSamples}
                error={errors.maxSamples}
                hint="auto, целое число или доля 0–1"
                onChange={(event) => update("maxSamples", event.target.value)}
              />
              <Input
                id="top-features"
                label="Признаков в объяснении"
                type="number"
                min={1}
                max={100}
                value={form.topFeatures}
                error={errors.topFeatures}
                onChange={(event) => update("topFeatures", Number(event.target.value))}
              />
              <Input
                id="top-pct"
                label="Доля на графиках"
                type="number"
                min={0.001}
                max={1}
                step={0.001}
                value={form.topPct}
                error={errors.topPct}
                onChange={(event) => update("topPct", Number(event.target.value))}
              />
              <Input
                id="top-n"
                label="Строк в UI/отчёте"
                type="number"
                min={1}
                max={500}
                value={form.topN}
                error={errors.topN}
                onChange={(event) => update("topN", Number(event.target.value))}
              />
            </div>
            <fieldset className="upload-picker">
              <legend>Нормализованные файлы</legend>
              {uploads.length ? (
                uploads.map((upload) => (
                  <label key={upload.id}>
                    <input
                      type="checkbox"
                      checked={form.uploadIds.includes(upload.id)}
                      onChange={() => toggleUpload(upload.id)}
                    />
                    <span>
                      <strong>{upload.filename}</strong>
                      <small>{formatDate(upload.normalized_at)}</small>
                    </span>
                  </label>
                ))
              ) : (
                <p className="muted">
                  Сначала нормализуйте хотя бы один файл в разделе «Загрузки».
                </p>
              )}
              {errors.uploadIds ? <p className="field-error">{errors.uploadIds}</p> : null}
            </fieldset>
            <div className="run-summary">
              <SlidersHorizontal />
              <div>
                <strong>
                  {statusLabel(form.scope)} · {form.uploadIds.length} файлов
                </strong>
                <small>
                  IF: {form.nEstimators} деревьев · LOF: {form.nNeighbors} соседей · показать top {form.topN}
                </small>
              </div>
            </div>
            <div className="form-actions">
              <Button
                type="submit"
                loading={submitting}
                disabled={!uploads.length || !canMutate}
                icon={<Play />}
              >
                Подтвердить и запустить
              </Button>
            </div>
          </form>
        </Card>
      ) : null}
      <section className="section-stack">
        <div className="table-toolbar">
          <div>
            <p className="section-label">История</p>
            <h2>Все запуски</h2>
          </div>
          <div className="filter-row">
            <Select
              id="status-filter"
              label="Статус"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">Все</option>
              <option value="queued">В очереди</option>
              <option value="running">Выполняется</option>
              <option value="completed">Завершён</option>
              <option value="failed">Ошибка</option>
            </Select>
            <Select
              id="scope-filter"
              label="Период"
              value={scopeFilter}
              onChange={(event) => setScopeFilter(event.target.value)}
            >
              <option value="">Все</option>
              <option value="day">День</option>
              <option value="week">Неделя</option>
              <option value="month">Месяц</option>
              <option value="range">Диапазон</option>
              <option value="all">Все данные</option>
            </Select>
          </div>
        </div>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} />
        ) : !filteredRuns.length ? (
          <EmptyState
            title="Запусков не найдено"
            description="Измените фильтры или создайте первый анализ."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <th>Запуск</th>
                <th>Период</th>
                <th>Статус</th>
                <th>Этап</th>
                <th>Попытка</th>
                <th>Создан</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link className="table-link mono" href={`/runs/${run.id}`}>
                      {shortId(run.id)}
                    </Link>
                  </td>
                  <td>
                    {statusLabel(run.scope)}
                    {run.target_date ? ` · ${run.target_date}` : ""}
                  </td>
                  <td>
                    <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
                  </td>
                  <td>{run.current_stage ? statusLabel(run.current_stage) : "—"}</td>
                  <td>{run.attempts}</td>
                  <td>{formatDate(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </div>
  );
}
