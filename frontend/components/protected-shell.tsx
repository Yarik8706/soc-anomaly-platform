"use client";

import { LoadingState } from "@/components/ui/states";
import { useSession } from "@/features/auth/session-provider";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { AppShell } from "./app-shell";

export function ProtectedShell({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) {
      const target = `${pathname}${window.location.search}`;
      router.replace(`/login?returnTo=${encodeURIComponent(target)}`);
    }
  }, [loading, pathname, router, user]);
  if (loading || !user)
    return (
      <div className="auth-loading">
        <LoadingState label="Проверяем сессию" />
      </div>
    );
  return <AppShell>{children}</AppShell>;
}

export function AdminGate({ children }: { children: ReactNode }) {
  const { user } = useSession();
  if (user?.role !== "admin")
    return (
      <div className="state-panel state-panel--error" role="alert">
        <h2>Недостаточно прав</h2>
        <p>Раздел доступен только администратору.</p>
      </div>
    );
  return children;
}
