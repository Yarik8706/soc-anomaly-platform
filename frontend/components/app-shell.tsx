"use client";

import {
  Activity,
  BarChart3,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldCheck,
  UploadCloud,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const navigation = [
  { href: "/", label: "Обзор", icon: LayoutDashboard },
  { href: "/uploads", label: "Загрузки", icon: UploadCloud },
  { href: "/runs", label: "Запуски", icon: Activity },
  { href: "/anomalies", label: "Аномалии", icon: ShieldCheck },
  { href: "/reports", label: "Отчёты", icon: FileText },
  { href: "/metrics", label: "Метрики", icon: BarChart3 },
  { href: "/admin/users", label: "Пользователи", icon: Users },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="app-shell">
      <button
        className="mobile-menu"
        onClick={() => setOpen((value) => !value)}
        aria-label={open ? "Закрыть меню" : "Открыть меню"}
        aria-expanded={open}
      >
        {open ? <X /> : <Menu />}
      </button>
      <aside className={`sidebar ${open ? "sidebar--open" : ""}`}>
        <Link href="/" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark">
            <ShieldCheck aria-hidden="true" />
          </span>
          <span>
            <strong>SOC Lens</strong>
            <small>Anomaly Platform</small>
          </span>
        </Link>
        <nav aria-label="Основная навигация">
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={active ? "nav-link nav-link--active" : "nav-link"}
                aria-current={active ? "page" : undefined}
                onClick={() => setOpen(false)}
              >
                <Icon aria-hidden="true" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <span className="system-dot" aria-hidden="true" />
          <span>
            <strong>Система доступна</strong>
            <small>API · Worker · DB</small>
          </span>
          <button aria-label="Выйти">
            <LogOut />
          </button>
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
