import { NextResponse } from "next/server";

type RouteParams = {
  params: Promise<{ path?: string[] }>;
};

const REQUEST_TIMEOUT_MS = 45000;
const IDEMPOTENT_RETRY_DELAYS_MS = [200, 600];

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

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriableProxyError(error: unknown) {
  const msg = String(error).toLowerCase();
  return (
    msg.includes("econnreset") ||
    msg.includes("socket hang up") ||
    msg.includes("etimedout") ||
    msg.includes("timeout") ||
    msg.includes("eai_again") ||
    msg.includes("fetch failed")
  );
}

function createProxyHeaders(request: Request) {
  const headers = new Headers();

  const incomingType = request.headers.get("content-type");
  if (incomingType) {
    headers.set("content-type", incomingType);
  }

  // Preserve range semantics so browser PDF preview can seek quickly.
  const passThroughHeaders = ["range", "if-range", "if-none-match", "if-modified-since"];
  for (const name of passThroughHeaders) {
    const value = request.headers.get(name);
    if (value) {
      headers.set(name, value);
    }
  }

  return headers;
}

function createResponseHeaders(response: Response) {
  const outHeaders = new Headers();
  const passHeaderNames = [
    "content-type",
    "content-disposition",
    "cache-control",
    "pragma",
    "expires",
    "etag",
    "last-modified",
    "content-length",
    "accept-ranges",
    "content-range",
  ];

  for (const name of passHeaderNames) {
    const value = response.headers.get(name);
    if (value) outHeaders.set(name, value);
  }

  return outHeaders;
}

async function fetchWithTimeout(target: string, init: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    return await fetch(target, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function proxyRequest(method: string, request: Request, params: RouteParams) {
  const { path = [] } = await params.params;
  const target = buildTargetUrl(request, path);
  const headers = createProxyHeaders(request);

  let body: string | undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = await request.text();
  }

  try {
    const canRetry = method === "GET" || method === "HEAD";
    let lastError: unknown;

    for (let attempt = 0; attempt <= IDEMPOTENT_RETRY_DELAYS_MS.length; attempt++) {
      try {
        const response = await fetchWithTimeout(target, {
          method,
          headers,
          body,
          cache: "no-store",
        });

        const outHeaders = createResponseHeaders(response);

        // Stream the upstream payload directly to the browser to reduce TTFB and
        // memory overhead for large files like PDF previews.
        return new Response(response.body, {
          status: response.status,
          headers: outHeaders,
        });
      } catch (error) {
        lastError = error;
        const shouldRetry = canRetry && attempt < IDEMPOTENT_RETRY_DELAYS_MS.length && isRetriableProxyError(error);
        if (!shouldRetry) {
          throw error;
        }
        await sleep(IDEMPOTENT_RETRY_DELAYS_MS[attempt]);
      }
    }

    throw lastError;
  } catch (error) {
    return NextResponse.json(
      { detail: `proxy_request_failed: ${String(error)}` },
      { status: 502 }
    );
  }
}

export async function GET(request: Request, context: RouteParams) {
  return proxyRequest("GET", request, context);
}

export async function HEAD(request: Request, context: RouteParams) {
  return proxyRequest("HEAD", request, context);
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
