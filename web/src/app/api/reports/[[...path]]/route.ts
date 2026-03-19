import { NextResponse } from "next/server";
import { createReadStream } from "node:fs";
import { access, stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

type RouteParams = {
  params: Promise<{ path?: string[] }>;
};

const REQUEST_TIMEOUT_MS = 45000;
const REPORT_FILE_TIMEOUT_MS = 180000;
const IDEMPOTENT_RETRY_DELAYS_MS = [200, 600];

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

function resolveReportsRoot() {
  const envPath = process.env.REPORTS_DIR?.trim();
  if (envPath) {
    return path.resolve(envPath);
  }
  // Next process cwd is usually <project>/web, reports are in ../storage/reports.
  return path.resolve(process.cwd(), "..", "storage", "reports");
}

function isLikelyReportFilePath(pathSegments: string[]) {
  if (pathSegments.length < 2) return false;
  const last = (pathSegments[pathSegments.length - 1] || "").toLowerCase();
  return /\.(pdf|docx|doc|txt)$/.test(last);
}

function parseRange(rangeHeader: string | null, fileSize: number) {
  if (!rangeHeader || !rangeHeader.startsWith("bytes=")) return null;
  const value = rangeHeader.slice(6).trim();
  const [startRaw, endRaw] = value.split("-", 2);
  if (!startRaw && !endRaw) return null;

  let start = startRaw ? Number(startRaw) : NaN;
  let end = endRaw ? Number(endRaw) : NaN;

  if (Number.isNaN(start)) {
    // bytes=-N => last N bytes
    const tail = Number(endRaw);
    if (!Number.isFinite(tail) || tail <= 0) return null;
    start = Math.max(fileSize - tail, 0);
    end = fileSize - 1;
  } else {
    if (Number.isNaN(end)) end = fileSize - 1;
  }

  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start || start >= fileSize) {
    return null;
  }

  end = Math.min(end, fileSize - 1);
  return { start, end };
}

async function tryServeLocalReport(request: Request, method: string, pathSegments: string[]) {
  if (method !== "GET" && method !== "HEAD") {
    return null;
  }

  // Two URL shapes are supported:
  //  1. /api/reports/{date}/{filename}.pdf  (path-segment style)
  //  2. /api/reports/preview?date={date}&filename={filename} (query-param style)
  let date: string;
  let filename: string;
  let inline = false;

  const isPreviewRoute = pathSegments.length === 1 && pathSegments[0] === "preview";
  if (isPreviewRoute) {
    const url = new URL(request.url);
    date = url.searchParams.get("date") ?? "";
    filename = url.searchParams.get("filename") ?? "";
    if (!/^\d{8}$/.test(date) || !filename || !/\.(pdf|docx|doc|txt)$/i.test(filename)) {
      return null;
    }
    inline = true;
  } else if (isLikelyReportFilePath(pathSegments)) {
    const [d, ...nameParts] = pathSegments;
    if (!/^\d{8}$/.test(d || "") || nameParts.length === 0) {
      return null;
    }
    date = d;
    filename = nameParts.join("/");
  } else {
    return null;
  }
  const reportsRoot = resolveReportsRoot();
  const candidate = path.resolve(reportsRoot, date, filename);
  const normalizedRoot = reportsRoot.endsWith(path.sep) ? reportsRoot : `${reportsRoot}${path.sep}`;
  if (!candidate.startsWith(normalizedRoot)) {
    return NextResponse.json({ detail: "invalid_report_path" }, { status: 400 });
  }

  try {
    await access(candidate);
  } catch {
    return null;
  }

  const info = await stat(candidate);
  if (!info.isFile()) {
    return null;
  }

  const isPdf = candidate.toLowerCase().endsWith(".pdf");
  const contentType = isPdf ? "application/pdf" : "application/octet-stream";
  const range = parseRange(request.headers.get("range"), info.size);
  const disposition = inline ? "inline" : "attachment";
  const contentDisposition = `${disposition}; filename="report${path.extname(candidate) || ""}"; filename*=UTF-8''${encodeURIComponent(path.basename(candidate))}`;

  const headers = new Headers({
    "content-type": contentType,
    "content-disposition": contentDisposition,
    "accept-ranges": "bytes",
    "cache-control": "private, max-age=60",
    "last-modified": new Date(info.mtimeMs).toUTCString(),
  });

  if (range) {
    const length = range.end - range.start + 1;
    headers.set("content-range", `bytes ${range.start}-${range.end}/${info.size}`);
    headers.set("content-length", String(length));
    if (method === "HEAD") {
      return new Response(null, { status: 206, headers });
    }
    const stream = createReadStream(candidate, { start: range.start, end: range.end });
    return new Response(Readable.toWeb(stream) as ReadableStream, { status: 206, headers });
  }

  headers.set("content-length", String(info.size));
  if (method === "HEAD") {
    return new Response(null, { status: 200, headers });
  }
  const stream = createReadStream(candidate);
  return new Response(Readable.toWeb(stream) as ReadableStream, { status: 200, headers });
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

async function fetchWithTimeout(target: string, init: RequestInit, timeoutMs: number) {
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

async function proxyRequest(method: string, request: Request, params: RouteParams) {
  const { path = [] } = await params.params;
  const localResponse = await tryServeLocalReport(request, method, path);
  if (localResponse) {
    return localResponse;
  }

  const target = buildTargetUrl(request, path);
  const headers = createProxyHeaders(request);
  const joinedPath = path.join("/").toLowerCase();
  const isReportFileRequest =
    path.length >= 2 &&
    /\.(pdf|docx|doc|txt)$/.test(joinedPath);

  let body: string | undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = await request.text();
  }

  try {
    const canRetry = method === "GET" || method === "HEAD";
    const timeoutMs = isReportFileRequest ? REPORT_FILE_TIMEOUT_MS : REQUEST_TIMEOUT_MS;
    const retryDelays = isReportFileRequest ? [] : IDEMPOTENT_RETRY_DELAYS_MS;
    let lastError: unknown;

    for (let attempt = 0; attempt <= retryDelays.length; attempt++) {
      try {
        const response = await fetchWithTimeout(target, {
          method,
          headers,
          body,
          cache: "no-store",
        }, timeoutMs);

        const outHeaders = createResponseHeaders(response);

        // Stream the upstream payload directly to the browser to reduce TTFB and
        // memory overhead for large files like PDF previews.
        return new Response(response.body, {
          status: response.status,
          headers: outHeaders,
        });
      } catch (error) {
        lastError = error;
        const shouldRetry = canRetry && attempt < retryDelays.length && isRetriableProxyError(error);
        if (!shouldRetry) {
          throw error;
        }
        await sleep(retryDelays[attempt]);
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
