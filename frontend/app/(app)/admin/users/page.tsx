import { AdminGate } from "@/components/protected-shell";
import { UserWorkspace } from "@/features/admin/user-workspace";

export default function UsersPage() {
  return (
    <AdminGate>
      <UserWorkspace />
    </AdminGate>
  );
}
