export const backendUrl = (process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8001").replace(
  /\/$/,
  "",
);
export const sessionCookie = "soc_session";

export async function backendRequest(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(`${backendUrl}${path}`, { ...init, cache: "no-store" });
  } catch {
    return Response.json(
      { detail: "Backend API недоступен. Проверьте, что сервис запущен." },
      { status: 502 },
    );
  }
}

export async function responsePayload(response: Response): Promise<unknown> {
  return response.json().catch(() => ({ detail: response.statusText }));
}
