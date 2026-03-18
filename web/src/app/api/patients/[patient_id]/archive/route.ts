import { NextResponse } from "next/server";

type RouteParams = {
  params: Promise<{ patient_id: string }>;
};

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

export async function POST(request: Request, { params }: RouteParams) {
  const { patient_id } = await params;
  const backendBase = resolveBackendBaseUrl();

  let payload: unknown = {};
  try {
    payload = await request.json();
  } catch {
    payload = {};
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(
      `${backendBase}/patients/${encodeURIComponent(patient_id)}/archive`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
        signal: controller.signal,
      }
    );

    const data = await response.json().catch(() => ({}));
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
