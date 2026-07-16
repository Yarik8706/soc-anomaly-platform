import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/states";

export default function MetricsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Model health"
        title="Метрики качества"
        description="Распределения score, стабильность топа и объясняющие признаки."
      />
      <EmptyState
        title="Метрики пока недоступны"
        description="Выберите завершённый запуск после появления результатов."
      />
    </div>
  );
}
