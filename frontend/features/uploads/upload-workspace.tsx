"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { UploadedFileRead } from "@/lib/api/types";
import { formatBytes, formatDate, shortId } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/status";
import { FileCheck2, FilePlus2, Trash2, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { MAX_BATCH_SIZE, mergeUploadFiles, validateUploadFile } from "./file-validation";

type QueueItem = {
  file: File;
  error: string | null;
  progress: number;
  state: "ready" | "uploading" | "success" | "error";
};

export function UploadWorkspace() {
  const [uploads, setUploads] = useState<UploadedFileRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const loadUploads = useCallback(async () => {
    setLoadError(null);
    try {
      setUploads(await apiFetch<UploadedFileRead[]>("/uploads"));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Не удалось получить загрузки");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    let active = true;
    apiFetch<UploadedFileRead[]>("/uploads")
      .then((items) => {
        if (active) setUploads(items);
      })
      .catch((error: unknown) => {
        if (active) {
          setLoadError(error instanceof Error ? error.message : "Не удалось получить загрузки");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function addFiles(incoming: File[]) {
    const files = mergeUploadFiles(
      queue.map(({ file }) => file),
      incoming,
    );
    setQueue(
      files.map((file) => ({ file, error: validateUploadFile(file), progress: 0, state: "ready" })),
    );
  }

  async function uploadBatch() {
    const valid = queue.filter((item) => !item.error && item.state !== "success");
    if (!valid.length) return;
    setQueue((items) =>
      items.map((item) =>
        valid.some(({ file }) => file === item.file)
          ? { ...item, state: "uploading", progress: 4 }
          : item,
      ),
    );
    const form = new FormData();
    valid.forEach(({ file }) => form.append("files", file));
    try {
      await new Promise<void>((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", "/api/backend/uploads/batch");
        request.setRequestHeader("Accept", "application/json");
        request.upload.onprogress = (event) => {
          if (!event.lengthComputable) return;
          const progress = Math.max(4, Math.round((event.loaded / event.total) * 100));
          setQueue((items) =>
            items.map((item) =>
              valid.some(({ file }) => file === item.file) ? { ...item, progress } : item,
            ),
          );
        };
        request.onload = () => {
          if (request.status >= 200 && request.status < 300) return resolve();
          let detail: unknown = request.statusText;
          try {
            detail = JSON.parse(request.responseText || "{}").detail;
          } catch {
            /* use status text */
          }
          reject(new ApiError(errorMessage(detail), request.status, detail));
        };
        request.onerror = () => reject(new Error("Сеть недоступна"));
        request.send(form);
      });
      setQueue((items) =>
        items.map((item) =>
          valid.some(({ file }) => file === item.file)
            ? { ...item, state: "success", progress: 100 }
            : item,
        ),
      );
      toast(`Загружено файлов: ${valid.length}`);
      await loadUploads();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Загрузка не выполнена";
      setQueue((items) =>
        items.map((item) =>
          valid.some(({ file }) => file === item.file)
            ? { ...item, state: "error", error: message }
            : item,
        ),
      );
      toast(message, "error");
    }
  }

  const readyCount = queue.filter(({ error, state }) => !error && state !== "success").length;
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Data ingestion"
        title="Загрузки"
        description="Проверьте и нормализуйте SIEM/NGFW файлы перед ML-анализом."
        actions={
          <Button icon={<FilePlus2 />} onClick={() => inputRef.current?.click()}>
            Выбрать файлы
          </Button>
        }
      />
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept=".csv,.tsv,.txt"
        multiple
        onChange={(event) => addFiles([...(event.target.files ?? [])])}
      />
      <Card
        className={`dropzone ${dragging ? "dropzone--active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles([...event.dataTransfer.files]);
        }}
      >
        <UploadCloud aria-hidden="true" />
        <div>
          <strong>Перетащите файлы сюда</strong>
          <p>CSV, TSV или TXT · до 50 МиБ · не более {MAX_BATCH_SIZE} за раз</p>
        </div>
      </Card>
      {queue.length ? (
        <Card className="queue-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Очередь загрузки</p>
              <h2>{queue.length} файлов</h2>
            </div>
            <Button
              loading={queue.some(({ state }) => state === "uploading")}
              disabled={!readyCount}
              onClick={uploadBatch}
              icon={<UploadCloud />}
            >
              Загрузить {readyCount || ""}
            </Button>
          </div>
          <div className="queue-list">
            {queue.map((item) => (
              <div
                className="queue-item"
                key={`${item.file.name}:${item.file.size}:${item.file.lastModified}`}
              >
                <FileCheck2 aria-hidden="true" />
                <div>
                  <strong>{item.file.name}</strong>
                  <small>
                    {formatBytes(item.file.size)} · {item.error ?? statusLabel(item.state)}
                  </small>
                  <span className="progress-track">
                    <span style={{ width: `${item.progress}%` }} />
                  </span>
                </div>
                <Badge
                  tone={
                    item.error ? "critical" : item.state === "success" ? "completed" : "neutral"
                  }
                >
                  {item.error ? "Ошибка" : statusLabel(item.state)}
                </Badge>
                <button
                  className="icon-button"
                  aria-label={`Убрать ${item.file.name}`}
                  onClick={() =>
                    setQueue((items) => items.filter(({ file }) => file !== item.file))
                  }
                >
                  <Trash2 />
                </button>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
      <section className="section-stack">
        <div className="section-heading">
          <div>
            <p className="eyebrow">История</p>
            <h2>Загруженные файлы</h2>
          </div>
          <span className="muted">{uploads.length} объектов</span>
        </div>
        {loading ? (
          <LoadingState />
        ) : loadError ? (
          <ErrorState
            message={loadError}
            action={<Button onClick={loadUploads}>Повторить</Button>}
          />
        ) : !uploads.length ? (
          <EmptyState
            title="Файлы ещё не загружены"
            description="Добавьте первый набор данных через область выше."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <th>Файл</th>
                <th>Размер</th>
                <th>Статус</th>
                <th>Создан</th>
                <th>ID</th>
              </tr>
            </thead>
            <tbody>
              {uploads.map((upload) => (
                <tr key={upload.id}>
                  <td>
                    <Link className="table-link" href={`/uploads/${upload.id}`}>
                      {upload.filename}
                    </Link>
                  </td>
                  <td>{formatBytes(upload.size)}</td>
                  <td>
                    <Badge tone={statusTone(upload.status)}>{statusLabel(upload.status)}</Badge>
                  </td>
                  <td>{formatDate(upload.created_at)}</td>
                  <td className="mono">{shortId(upload.id)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </div>
  );
}
