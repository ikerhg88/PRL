export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";
const sessionStorageKey = "iprl_cae_session";
const selectedCompanyStorageKey = "iprl_cae_selected_company";

export const tenantHeaders: Record<string, string> = {};

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: mergedHeaders(init.headers)
  });
  if (!response.ok) {
    const text = await response.text();
    handleUnauthorized(path, response.status);
    throw new Error(formatApiError(text, response.status));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function apiBlob(path: string, init: RequestInit = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: mergedHeaders(init.headers)
  });
  if (!response.ok) {
    const text = await response.text();
    handleUnauthorized(path, response.status);
    throw new Error(formatApiError(text, response.status));
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition"))
  };
}

export function jsonHeaders() {
  return { "Content-Type": "application/json" };
}

export function authHeaders(): Record<string, string> {
  const session = readSessionHeaderData();
  if (session) {
    return {
      Authorization: `Bearer ${session.access_token}`,
      "X-Tenant-ID": String(session.tenant_id),
      "X-User-ID": String(session.user.id)
    };
  }
  return {};
}

function mergedHeaders(extraHeaders?: HeadersInit) {
  const headers = new Headers(authHeaders());
  if (extraHeaders) {
    new Headers(extraHeaders).forEach((value, key) => headers.set(key, value));
  }
  return headers;
}

export function formatApiError(text: string, status: number) {
  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    return typeof payload.detail === "string" ? payload.detail : `HTTP ${status}: ${JSON.stringify(payload.detail ?? payload)}`;
  } catch {
    return `HTTP ${status}: ${text}`;
  }
}

function filenameFromDisposition(disposition: string | null) {
  if (!disposition) {
    return null;
  }
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return match?.[1] ?? null;
}

function readSessionHeaderData(): { access_token: string; tenant_id: number; user: { id: number } } | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(sessionStorageKey);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as { access_token: string; tenant_id: number; user: { id: number } };
  } catch {
    window.localStorage.removeItem(sessionStorageKey);
    return null;
  }
}

function handleUnauthorized(path: string, status: number) {
  if (status !== 401 || typeof window === "undefined" || path.includes("/api/v1/auth/login")) {
    return;
  }
  window.localStorage.removeItem(sessionStorageKey);
  window.localStorage.removeItem(selectedCompanyStorageKey);
  const nextPath = `${window.location.pathname}${window.location.search}`;
  window.location.href = `/login?next=${encodeURIComponent(nextPath)}`;
}
