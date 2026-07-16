import { AlertTriangle, Database, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({ label = "Загружаем данные" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="spin" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-panel">
      <Database aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <AlertTriangle aria-hidden="true" />
      <h2>Не удалось загрузить данные</h2>
      <p>{message}</p>
      {action}
    </div>
  );
}
