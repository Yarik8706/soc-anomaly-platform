import { backendRequest, responsePayload, sessionCookie } from "@/lib/server/backend";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const credentials = await request.json().catch(() => null);
  if (
    !credentials ||
    typeof credentials.email !== "string" ||
    typeof credentials.password !== "string"
  ) {
    return NextResponse.json({ detail: "Укажите email и пароль." }, { status: 400 });
  }
  const login = await backendRequest("/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ email: credentials.email, password: credentials.password }),
  });
  if (!login.ok) return NextResponse.json(await responsePayload(login), { status: login.status });
  const token = (await login.json()) as { access_token: string; expires_in: number };
  const me = await backendRequest("/auth/me", {
    headers: { authorization: `Bearer ${token.access_token}`, accept: "application/json" },
  });
  if (!me.ok) return NextResponse.json(await responsePayload(me), { status: me.status });
  const result = NextResponse.json(await me.json());
  result.cookies.set(sessionCookie, token.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.SESSION_COOKIE_SECURE !== "false" && process.env.NODE_ENV === "production",
    path: "/",
    maxAge: token.expires_in,
  });
  return result;
}
