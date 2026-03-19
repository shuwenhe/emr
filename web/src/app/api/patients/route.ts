import { readFile } from "node:fs/promises";
import path from "node:path";
import mysql, { type Pool, type RowDataPacket } from "mysql2/promise";
import { NextResponse } from "next/server";
import YAML from "yaml";

function resolveBackendBaseUrl() {
  const envBase = process.env.BACKEND_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

type MysqlConfig = {
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
};

type PatientRow = RowDataPacket & {
  patient_id: string;
  name: string | null;
  gender: string | null;
  age: number | null;
  archived: number | boolean | null;
  deleted: number | boolean | null;
  payload_json: string | Record<string, unknown> | null;
  updated_at: Date | string | null;
};

let _mysqlPoolPromise: Promise<Pool | null> | null = null;

function resolveMysqlConfigPath() {
  return path.resolve(process.cwd(), "..", "config", "mysql.yaml");
}

async function loadMysqlConfig(): Promise<MysqlConfig | null> {
  const envHost = process.env.MYSQL_HOST?.trim();
  const envPort = Number(process.env.MYSQL_PORT || 3306);
  const envUser = process.env.MYSQL_USER?.trim();
  const envPassword = process.env.MYSQL_PASSWORD ?? "";
  const envDatabase = process.env.MYSQL_DB?.trim() || process.env.MYSQL_DATABASE?.trim();
  if (envHost && envUser && envDatabase) {
    return {
      host: envHost,
      port: Number.isFinite(envPort) ? envPort : 3306,
      user: envUser,
      password: envPassword,
      database: envDatabase,
    };
  }

  try {
    const raw = await readFile(resolveMysqlConfigPath(), "utf-8");
    const parsed = YAML.parse(raw) as { mysql?: Partial<MysqlConfig> } | null;
    const cfg = parsed?.mysql;
    if (!cfg?.host || !cfg?.user || !cfg?.database) {
      return null;
    }
    return {
      host: String(cfg.host),
      port: Number(cfg.port || 3306),
      user: String(cfg.user),
      password: String(cfg.password || ""),
      database: String(cfg.database),
    };
  } catch {
    return null;
  }
}

async function getMysqlPool(): Promise<Pool | null> {
  if (_mysqlPoolPromise) return _mysqlPoolPromise;
  _mysqlPoolPromise = (async () => {
    const config = await loadMysqlConfig();
    if (!config) return null;
    return mysql.createPool({
      host: config.host,
      port: config.port,
      user: config.user,
      password: config.password,
      database: config.database,
      waitForConnections: true,
      connectionLimit: 5,
      queueLimit: 0,
      connectTimeout: 3000,
      enableKeepAlive: true,
    });
  })();
  return _mysqlPoolPromise;
}

function parsePayloadJson(value: PatientRow["payload_json"]) {
  if (!value) return {};
  if (typeof value === "object") return value;
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}

async function fetchPatientsFromDatabase(searchParams: URLSearchParams): Promise<unknown[] | null> {
  const pool = await getMysqlPool();
  if (!pool) return null;

  const page = Math.max(1, Number(searchParams.get("page") || 1));
  const limit = Math.max(1, Math.min(200, Number(searchParams.get("limit") || 20)));
  const offset = (page - 1) * limit;
  const includeArchived = searchParams.get("include_archived") === "true";
  const includeDeleted = searchParams.get("include_deleted") === "true";

  const [rows] = await pool.query<PatientRow[]>(
    `
      SELECT patient_id, name, gender, age, archived, deleted, payload_json, updated_at
      FROM patients
      WHERE (? = 1 OR COALESCE(archived, 0) = 0)
        AND (? = 1 OR COALESCE(deleted, 0) = 0)
      ORDER BY updated_at DESC
      LIMIT ? OFFSET ?
    `,
    [includeArchived ? 1 : 0, includeDeleted ? 1 : 0, limit, offset]
  );

  return rows.map((row) => ({
    patient_id: row.patient_id,
    name: row.name,
    gender: row.gender,
    age: row.age,
    archived: Boolean(row.archived),
    deleted: Boolean(row.deleted),
    updated_at:
      row.updated_at instanceof Date
        ? row.updated_at.toISOString()
        : row.updated_at
          ? new Date(row.updated_at).toISOString()
          : null,
    ...parsePayloadJson(row.payload_json),
  }));
}

// ─── In-process stale-while-revalidate cache ───────────────────────────────
// Key: full query string (e.g. "page=1&limit=20")
// Returns cached data immediately while the background refresh runs,
// so patients list never stalls waiting for a busy LLM backend.
const CACHE_TTL_MS = 8_000;        // serve fresh data up to 8 s old
const CACHE_MAX_STALE_MS = 300_000; // serve stale data up to 5 min while refreshing in background
const FETCH_TIMEOUT_MS = 25_000;

type CacheEntry = {
  data: unknown;
  status: number;
  fetchedAt: number;
  refreshing: boolean;
};

const _cache = new Map<string, CacheEntry>();

async function fetchPatients(
  searchParams: URLSearchParams,
  target: string
): Promise<{ data: unknown; status: number; source: "db" | "backend" }> {
  const dbData = await fetchPatientsFromDatabase(searchParams).catch(() => null);
  if (dbData) {
    return { data: dbData, status: 200, source: "db" };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(target, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    const data = await response.json().catch(() => []);
    return { data, status: response.status, source: "backend" };
  } finally {
    clearTimeout(timer);
  }
}

async function getCachedPatients(
  cacheKey: string,
  searchParams: URLSearchParams,
  target: string
): Promise<NextResponse> {
  const now = Date.now();
  const entry = _cache.get(cacheKey);

  // Has real (previously fetched) data
  const hasData = entry != null && entry.fetchedAt > 0;
  const age = hasData ? now - entry.fetchedAt : Infinity;

  // Fresh hit — return immediately
  if (hasData && age < CACHE_TTL_MS) {
    return NextResponse.json(entry.data, {
      status: entry.status,
      headers: { "x-cache": "HIT" },
    });
  }

  // Stale or expired but has real data — return immediately + background refresh
  if (hasData) {
    if (!entry.refreshing) {
      entry.refreshing = true;
      fetchPatients(searchParams, target)
        .then(({ data, status }) => {
          _cache.set(cacheKey, { data, status, fetchedAt: Date.now(), refreshing: false });
        })
        .catch(() => {
          const current = _cache.get(cacheKey);
          if (current === entry) entry.refreshing = false;
        });
    }
    return NextResponse.json(entry.data, {
      status: entry.status,
      headers: { "x-cache": age < CACHE_MAX_STALE_MS ? "STALE" : "STALE-EXPIRED" },
    });
  }

  // No cache yet: try direct DB read synchronously so UI can render immediately.
  try {
    const { data, status, source } = await fetchPatients(searchParams, target);
    _cache.set(cacheKey, { data, status, fetchedAt: Date.now(), refreshing: false });
    return NextResponse.json(data, {
      status,
      headers: { "x-cache": source === "db" ? "MISS-DB" : "MISS" },
    });
  } catch {
    // Fall through to non-blocking warm-up if both DB and backend are unavailable.
  }

  // No real data yet — start background fetch if not already running
  if (!entry) {
    const placeholder: CacheEntry = { data: [], status: 200, fetchedAt: 0, refreshing: true };
    _cache.set(cacheKey, placeholder);
    fetchPatients(searchParams, target)
      .then(({ data, status }) => {
        _cache.set(cacheKey, { data, status, fetchedAt: Date.now(), refreshing: false });
      })
      .catch(() => {
        // Remove placeholder so next poll retries the backend
        _cache.delete(cacheKey);
      });
  }

  // Return WARMING immediately — client polls until real data arrives
  return NextResponse.json([], {
    status: 200,
    headers: { "x-cache": "WARMING", "retry-after": "3" },
  });
}

export async function GET(request: Request) {
  const backendBase = resolveBackendBaseUrl();
  const incomingUrl = new URL(request.url);
  const queryString = incomingUrl.searchParams.toString();
  const target = `${backendBase}/patients${queryString ? `?${queryString}` : ""}`;
  return getCachedPatients(queryString, incomingUrl.searchParams, target);
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
    if (response.ok) {
      // Invalidate all patient list cache entries so next GET fetches fresh data
      _cache.clear();
    }
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: `proxy_request_failed: ${String(error)}` },
      { status: 502 }
    );
  }
}
