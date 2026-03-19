import { NextResponse } from "next/server";

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

export async function GET(request: Request) {
  const backendBase = resolveBackendBaseUrl();
  const incomingUrl = new URL(request.url);
  const queryString = incomingUrl.searchParams.toString();
  const target = `${backendBase}/patients${queryString ? `?${queryString}` : ""}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(target, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ([]));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: `proxy_request_failed: ${String(error)}` },
      { status: 502 }
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const response = await fetch(`${resolveBackendBaseUrl()}/patients`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: `proxy_request_failed: ${String(error)}` },
      { status: 502 }
    );
  }
}
