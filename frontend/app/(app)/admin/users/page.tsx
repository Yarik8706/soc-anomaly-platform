import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/states";

export default function UsersPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administration"
        title="Пользователи"
        description="Учётные записи и ролевой доступ к платформе."
      />
      <EmptyState
        title="Раздел загружается"
        description="Данные пользователей появятся после подключения сессии."
      />
    </div>
  );
}
