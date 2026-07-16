import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/states";

export default function ReportsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Reporting"
        title="SOC-отчёты"
        description="Сводки расследований в Markdown и PDF."
      />
      <EmptyState
        title="Отчётов пока нет"
        description="Создайте отчёт из карточки завершённого запуска."
      />
    </div>
  );
}
