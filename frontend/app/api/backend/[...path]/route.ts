import { type NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8001";
const sessionCookie = "soc_session";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const target = new URL(path.join("/"), `${backendUrl.replace(/\/$/, "")}/`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of ["accept", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const token = request.cookies.get(sessionCookie)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);

  const method = request.method;
  const response = await fetch(target, {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  for (const name of ["content-type", "content-disposition"]) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  const result = new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
  if (response.status === 401) result.cookies.delete(sessionCookie);
  return result;
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
