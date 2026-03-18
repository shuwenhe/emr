import { NextResponse } from "next/server";

type RouteParams = {
  params: Promise<{ path?: string[] }>;
};

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

function buildTargetUrl(request: Request, pathSegments: string[]) {
  const backendBase = resolveBackendBaseUrl();
  const incoming = new URL(request.url);
  const suffix = pathSegments.length > 0 ? `/${pathSegments.map(encodeURIComponent).join("/")}` : "";
  const query = incoming.searchParams.toString();
  return `${backendBase}/reports${suffix}${query ? `?${query}` : ""}`;
}

async function proxyRequest(method: string, request: Request, params: RouteParams) {
  const { path = [] } = await params.params;
  const target = buildTargetUrl(request, path);

  const headers = new Headers();
  const incomingType = request.headers.get("content-type");
  if (incomingType) {
    headers.set("content-type", incomingType);
  }

  let body: string | undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = await request.text();
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      signal: controller.signal,
    });

    const outHeaders = new Headers();
    const passHeaderNames = [
      "content-type",
      "content-disposition",
      "cache-control",
      "pragma",
      "expires",
      "etag",
      "last-modified",
    ];
    for (const name of passHeaderNames) {
      const value = response.headers.get(name);
      if (value) outHeaders.set(name, value);
    }

    const payload = await response.arrayBuffer();
    return new Response(payload, {
      status: response.status,
      headers: outHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      { detail: `proxy_request_failed: ${String(error)}` },
      { status: 502 }
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function GET(request: Request, context: RouteParams) {
  return proxyRequest("GET", request, context);
}

export async function POST(request: Request, context: RouteParams) {
  return proxyRequest("POST", request, context);
}

export async function PUT(request: Request, context: RouteParams) {
  return proxyRequest("PUT", request, context);
}

export async function DELETE(request: Request, context: RouteParams) {
  return proxyRequest("DELETE", request, context);
}
