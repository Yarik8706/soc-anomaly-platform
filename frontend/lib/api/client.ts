import { ApiError, errorMessage } from "@/lib/api/errors";

const API_PREFIX = "/api/backend";

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", headers.get("Accept") ?? "application/json");

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined")
      window.dispatchEvent(new Event("soc:unauthorized"));
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = payload?.detail ?? payload;
    throw new ApiError(errorMessage(detail), response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiText(path: string, init: RequestInit = {}): Promise<string> {
  const response = await fetch(`${API_PREFIX}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined")
      window.dispatchEvent(new Event("soc:unauthorized"));
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = payload?.detail ?? payload;
    throw new ApiError(errorMessage(detail), response.status, detail);
  }
  return response.text();
}

export function toQuery(values: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}
