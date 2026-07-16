import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/states";

export default function AnomaliesPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Analyst workspace"
        title="Аномалии"
        description="Сигналы по пользователям и хостам, требующие внимания."
      />
      <EmptyState
        title="Аномалий пока нет"
        description="После завершённого запуска результаты появятся здесь."
      />
    </div>
  );
}
