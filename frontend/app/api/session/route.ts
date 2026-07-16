import { backendRequest, responsePayload, sessionCookie } from "@/lib/server/backend";
import { type NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const token = request.cookies.get(sessionCookie)?.value;
  if (!token) return NextResponse.json({ detail: "Сессия отсутствует" }, { status: 401 });
  const response = await backendRequest("/auth/me", {
    headers: { authorization: `Bearer ${token}`, accept: "application/json" },
  });
  const result = NextResponse.json(await responsePayload(response), { status: response.status });
  if (response.status === 401) result.cookies.delete(sessionCookie);
  return result;
}

export async function DELETE() {
  const result = new NextResponse(null, { status: 204 });
  result.cookies.delete(sessionCookie);
  return result;
}
