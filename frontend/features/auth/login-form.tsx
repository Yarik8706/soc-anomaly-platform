"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { useSession } from "@/features/auth/session-provider";
import { ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export function LoginForm({ returnTo }: { returnTo: string }) {
  const { user, loading, login } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!loading && user) router.replace(returnTo);
  }, [loading, returnTo, router, user]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace(returnTo);
    } catch {
      setError("Не удалось войти. Проверьте email и пароль.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-brand">
          <span className="brand-mark">
            <ShieldCheck />
          </span>
          <div>
            <strong>SOC Lens</strong>
            <small>Anomaly Platform</small>
          </div>
        </div>
        <div>
          <p className="eyebrow">Secure workspace</p>
          <h1>Вход в платформу</h1>
          <p>
            Используйте учётную запись SOC-команды. Сессия хранится в защищённой HttpOnly cookie.
          </p>
        </div>
        <form onSubmit={submit}>
          <Input
            id="login-email"
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            id="login-password"
            label="Пароль"
            type="password"
            autoComplete="current-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error ? (
            <p className="login-error" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" loading={busy} disabled={loading}>
            Войти
          </Button>
        </form>
        <small className="login-note">
          Доступ и действия журналируются для аудита безопасности.
        </small>
      </section>
      <section className="login-aside">
        <p className="eyebrow">Operational clarity</p>
        <h2>От сырого события до проверяемого решения.</h2>
        <ol>
          <li>
            <span>01</span>
            <div>
              <strong>Нормализация</strong>
              <small>Единый поток SIEM и NGFW</small>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>ML-анализ</strong>
              <small>Ранжирование и explainability</small>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>Расследование</strong>
              <small>Workflow с полным audit trail</small>
            </div>
          </li>
        </ol>
      </section>
    </main>
  );
}
