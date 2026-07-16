import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/states";

export default function RunsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Analysis pipeline"
        title="Запуски анализа"
        description="Очередь, этапы и результаты ML-обработки."
      />
      <EmptyState
        title="Запусков пока нет"
        description="Подготовьте данные и создайте первый анализ."
      />
    </div>
  );
}
