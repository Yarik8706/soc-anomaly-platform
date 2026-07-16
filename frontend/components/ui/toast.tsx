"use client";

import { CheckCircle2, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type ToastTone = "success" | "error";
type ToastItem = { id: number; message: string; tone: ToastTone };
const ToastContext = createContext<(message: string, tone?: ToastTone) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((message: string, tone: ToastTone = "success") => {
    const id = Date.now();
    setItems((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 5000);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite">
        {items.map((item) => (
          <div className={`toast toast--${item.tone}`} key={item.id}>
            {item.tone === "success" ? <CheckCircle2 /> : <XCircle />}
            <span>{item.message}</span>
            <button
              aria-label="Закрыть уведомление"
              onClick={() => setItems((current) => current.filter(({ id }) => id !== item.id))}
            >
              <X />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
