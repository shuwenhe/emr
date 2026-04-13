import { NextResponse } from "next/server";

type RouteParams = {
  params: Promise<{ path?: string[] }>;
};

const REQUEST_TIMEOUT_MS = 120_000;
const BATCH_REQUEST_TIMEOUT_MS = 600_000;

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
  return `${backendBase}/ingest${suffix}${query ? `?${query}` : ""}`;
}

function copySafeRequestHeaders(request: Request) {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  const accept = request.headers.get("accept");
  if (accept) {
    headers.set("accept", accept);
  }
  return headers;
}

async function fetchWithTimeout(target: string, init: RequestInit, timeoutMs: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(target, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function proxyRequest(method: string, request: Request, params: RouteParams) {
  const { path = [] } = await params.params;
  const normalizedPath = normalizePathSegments(path);
  const target = buildTargetUrl(request, normalizedPath);
  const isBatchIngest = normalizedPath.join("/") === "batch";

  try {
    const init: RequestInit & { duplex?: "half" } = {
      method,
      cache: "no-store",
      headers: copySafeRequestHeaders(request),
    };

    if (method !== "GET" && method !== "HEAD") {
      // Stream request body directly to backend to avoid buffering large
      // multipart uploads in Next.js memory.
      init.body = request.body;
      init.duplex = "half";
    }

    const timeoutMs = isBatchIngest ? BATCH_REQUEST_TIMEOUT_MS : REQUEST_TIMEOUT_MS;
    const upstream = await fetchWithTimeout(target, init, timeoutMs);
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
    const message = String(error || "");
    const detail = /ECONNREFUSED|fetch failed|network/i.test(message)
      ? "ingest_proxy_failed: backend_unreachable"
      : `ingest_proxy_failed: ${message}`;
    return NextResponse.json({ detail }, { status: 502 });
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

export async function HEAD(request: Request, context: RouteParams) {
  return proxyRequest("HEAD", request, context);
}
