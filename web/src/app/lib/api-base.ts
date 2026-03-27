export function resolveApiBase(): string {
  const envBase = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "") || "/api";
  }
  return "/api";
}
