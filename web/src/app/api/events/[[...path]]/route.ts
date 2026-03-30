import { NextResponse } from "next/server";

type RouteParams = {
  params: Promise<{ path?: string[] }>;
};

const REQUEST_TIMEOUT_MS = 45000;
const SSE_TIMEOUT_MS = 0;

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

function safeDecodeSegment(segment: string) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function normalizePathSegments(pathSegments: string[]) {
  return pathSegments.map((segment) => safeDecodeSegment(String(segment || "")));
}

function buildTargetUrl(request: Request, pathSegments: string[]) {
  const backendBase = resolveBackendBaseUrl();
  const incoming = new URL(request.url);
  const suffix = pathSegments.length > 0 ? `/${pathSegments.map(encodeURIComponent).join("/")}` : "";
  const query = incoming.searchParams.toString();
  return `${backendBase}/events${suffix}${query ? `?${query}` : ""}`;
}

function isSseRequest(pathSegments: string[]) {
  // e.g. /events/ingest-progress/{record_id}
  // latest endpoint is JSON and should not be treated as SSE.
  if (pathSegments.length < 2) return false;
  if (pathSegments[0] !== "ingest-progress") return false;
  if (pathSegments[pathSegments.length - 1] === "latest") return false;
  return true;
}

async function fetchWithTimeout(target: string, init: RequestInit, timeoutMs: number) {
  if (timeoutMs <= 0) {
    return fetch(target, init);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(target, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function proxyGet(request: Request, params: RouteParams) {
  const { path = [] } = await params.params;
  const normalizedPath = normalizePathSegments(path);
  const target = buildTargetUrl(request, normalizedPath);
  const sse = isSseRequest(normalizedPath);

  try {
    const upstream = await fetchWithTimeout(
      target,
      {
        method: "GET",
        headers: {
          Accept: sse ? "text/event-stream" : "application/json, text/plain, */*",
          "Cache-Control": "no-cache",
        },
        cache: "no-store",
      },
      sse ? SSE_TIMEOUT_MS : REQUEST_TIMEOUT_MS
    );

    if (!upstream.ok) {
      const detail = await upstream.text().catch(() => "");
      return NextResponse.json(
        { detail: detail || `events_proxy_failed_http_${upstream.status}` },
        { status: upstream.status }
      );
    }

    if (sse) {
      if (!upstream.body) {
        return NextResponse.json({ detail: "events_proxy_empty_stream" }, { status: 502 });
      }
      const headers = new Headers();
      headers.set("Content-Type", "text/event-stream");
      headers.set("Cache-Control", "no-cache");
      headers.set("Connection", "keep-alive");
      headers.set("X-Accel-Buffering", "no");
      return new Response(upstream.body, { status: 200, headers });
    }

    const contentType = upstream.headers.get("content-type") || "application/json";
    const bodyText = await upstream.text();
    return new Response(bodyText, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { detail: `events_proxy_failed: ${String(error)}` },
      { status: 502 }
    );
  }
}

export async function GET(request: Request, context: RouteParams) {
  return proxyGet(request, context);
}
