import { AdminGate } from "@/components/protected-shell";
import { AuditWorkspace } from "@/features/admin/audit-workspace";

export default function AuditPage() {
  return (
    <AdminGate>
      <AuditWorkspace />
    </AdminGate>
  );
}
