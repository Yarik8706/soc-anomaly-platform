"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";
import type { NormalizedArtifact, UploadedFileRead } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { CheckCircle2, ChevronLeft, FileCog, WandSparkles, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

export function UploadDetail({ id }: { id: string }) {
  const [upload, setUpload] = useState<UploadedFileRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"validate" | "normalize" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const load = useCallback(async () => {
    setError(null);
    try {
      setUpload(await apiFetch<UploadedFileRead>(`/uploads/${id}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Файл не найден");
    } finally {
      setLoading(false);
    }
  }, [id]);
  useEffect(() => {
    let active = true;
    apiFetch<UploadedFileRead>(`/uploads/${id}`)
      .then((item) => {
        if (active) setUpload(item);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "Файл не найден");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  async function runAction(action: "validate" | "normalize") {
    setBusy(action);
    try {
      setUpload(await apiFetch<UploadedFileRead>(`/uploads/${id}/${action}`, { method: "POST" }));
      toast(action === "validate" ? "Проверка завершена" : "Нормализация завершена");
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : "Действие не выполнено", "error");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <LoadingState label="Загружаем карточку файла" />;
  if (error || !upload)
    return (
      <ErrorState
        message={error ?? "Файл не найден"}
        action={<Button onClick={load}>Повторить</Button>}
      />
    );
  const validation = upload.validation_result;
  const normalization = upload.normalization_result;
  return (
    <div className="page-stack">
      <Link className="back-link" href="/uploads">
        <ChevronLeft />К загрузкам
      </Link>
      <PageHeader
        eyebrow="Карточка файла"
        title={upload.filename}
        description={`${formatBytes(upload.size)} · загружен ${formatDate(upload.created_at)}`}
        actions={
          <>
            <Button
              variant="secondary"
              loading={busy === "validate"}
              disabled={Boolean(busy)}
              icon={<FileCog />}
              onClick={() => runAction("validate")}
            >
              Проверить
            </Button>
            <Button
              loading={busy === "normalize"}
              disabled={Boolean(busy) || upload.status === "invalid"}
              icon={<WandSparkles />}
              onClick={() => runAction("normalize")}
            >
              Нормализовать
            </Button>
          </>
        }
      />
      <section className="detail-grid">
        <Card className="detail-card">
          <p className="eyebrow">Состояние</p>
          <Badge tone={statusTone(upload.status)}>{statusLabel(upload.status)}</Badge>
          <dl className="definition-list">
            <div>
              <dt>ID</dt>
              <dd className="mono">{upload.id}</dd>
            </div>
            <div>
              <dt>Content type</dt>
              <dd>{upload.content_type}</dd>
            </div>
            <div>
              <dt>Владелец</dt>
              <dd className="mono">{upload.uploaded_by ?? "—"}</dd>
            </div>
            <div>
              <dt>Проверен</dt>
              <dd>{formatDate(upload.validated_at)}</dd>
            </div>
            <div>
              <dt>Нормализован</dt>
              <dd>{formatDate(upload.normalized_at)}</dd>
            </div>
          </dl>
        </Card>
        <Card className="detail-card detail-card--wide">
          <p className="eyebrow">Проверка структуры</p>
          {validation ? (
            <>
              <div
                className={`result-banner ${validation.is_valid ? "result-banner--success" : "result-banner--error"}`}
              >
                {validation.is_valid ? <CheckCircle2 /> : <XCircle />}
                <div>
                  <strong>
                    {validation.is_valid
                      ? "Структура подходит для анализа"
                      : "Найдены ошибки структуры"}
                  </strong>
                  <small>
                    {validation.encoding ?? "кодировка неизвестна"} · разделитель{" "}
                    {JSON.stringify(validation.delimiter)} · {validation.sampled_rows} строк выборки
                  </small>
                </div>
              </div>
              {validation.errors.length ? (
                <ul className="error-list">
                  {validation.errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : null}
              <div className="chip-list">
                {validation.columns.map((column) => (
                  <span className="chip" key={column}>
                    {column}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="muted">Файл ещё не проверялся. Запустите проверку структуры.</p>
          )}
        </Card>
      </section>
      <Card className="detail-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Артефакты</p>
            <h2>Результат нормализации</h2>
          </div>
          {normalization?.processed_rows !== undefined ? (
            <span className="muted">
              Обработано {normalization.processed_rows}, пропущено {normalization.skipped_rows ?? 0}
            </span>
          ) : null}
        </div>
        {normalization?.errors?.length ? (
          <ul className="error-list">
            {normalization.errors.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : normalization?.artifacts?.length ? (
          <ArtifactList artifacts={normalization.artifacts} />
        ) : (
          <p className="muted">Артефакты появятся после успешной нормализации.</p>
        )}
      </Card>
    </div>
  );
}

function ArtifactList({ artifacts }: { artifacts: NormalizedArtifact[] }) {
  return (
    <div className="artifact-list">
      {artifacts.map((artifact) => (
        <div key={artifact.path}>
          <span>
            <strong>{artifact.path.split("/").pop()}</strong>
            <small>
              {artifact.source} · {artifact.date}
            </small>
          </span>
          <Badge>{artifact.rows} строк</Badge>
        </div>
      ))}
    </div>
  );
}
