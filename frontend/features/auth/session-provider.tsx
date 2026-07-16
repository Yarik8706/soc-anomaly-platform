"use client";

import type { UserRead } from "@/lib/api/types";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface SessionContextValue {
  user: UserRead | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<UserRead>;
  logout: () => Promise<void>;
  canMutate: boolean;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    fetch("/api/session", { cache: "no-store" })
      .then(async (response) => {
        if (active) setUser(response.ok ? ((await response.json()) as UserRead) : null);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const unauthorized = () => setUser(null);
    window.addEventListener("soc:unauthorized", unauthorized);
    return () => {
      active = false;
      window.removeEventListener("soc:unauthorized", unauthorized);
    };
  }, []);
  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch("/api/session/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(typeof payload.detail === "string" ? payload.detail : "Не удалось войти");
    }
    const value = (await response.json()) as UserRead;
    setUser(value);
    return value;
  }, []);
  const logout = useCallback(async () => {
    await fetch("/api/session", { method: "DELETE" });
    setUser(null);
  }, []);
  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      canMutate: user?.role === "admin" || user?.role === "analyst",
    }),
    [user, loading, login, logout],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
