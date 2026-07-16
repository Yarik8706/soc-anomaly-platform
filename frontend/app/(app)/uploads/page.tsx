import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/states";

export default function UploadsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Data ingestion"
        title="Загрузки"
        description="Входные SIEM и NGFW файлы и состояние их обработки."
      />
      <EmptyState
        title="Файлы ещё не загружены"
        description="Загрузите CSV, TSV или TXT, чтобы начать анализ."
      />
    </div>
  );
}
