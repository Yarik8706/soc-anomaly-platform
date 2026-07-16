import { ProtectedShell } from "@/components/protected-shell";

export default function ProductLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedShell>{children}</ProtectedShell>;
}
