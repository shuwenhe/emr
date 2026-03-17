import { NextResponse } from "next/server";

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
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
