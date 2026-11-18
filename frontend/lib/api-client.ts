/**
 * Centralised API client.
 *
 * - Sends cookies (HttpOnly auth cookies are set by the backend in Phase 2).
 * - Attaches the CSRF token header for unsafe methods when the cookie is present.
 * - Normalises backend error envelopes into `ApiError`.
 */
import { apiBase } from "@/lib/env";
import { askReauth, notifyLocked } from "@/lib/privacy-bus";
import { credentialsMode, panelHeaders, panelSession, refreshPanelSession } from "@/lib/panel-session";
import type { ApiErrorBody } from "@/types/api";

export class ApiError extends Error {
  status: number;
  code: string;
  errors?: unknown;
  requestId?: string;
  /** The whole error body: some errors carry data for the next step (e.g. `mfa_token`). */
  body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null, fallback = "Request failed") {
    super(body?.detail ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? "unknown_error";
    this.errors = body?.errors;
    this.requestId = body?.request_id;
    this.body = body;
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions extends Omit<RequestInit, "method" | "body"> {
  method?: Method;
  body?: unknown;
  /** Optional organization context for multi-organization staff accounts. */
  organizationId?: string;
  searchParams?: Record<string, string | number | boolean | undefined | null>;
}

let defaultOrganizationId: string | undefined;
/** Set once by the auth provider so every request carries the active organization. */
export function setDefaultOrganizationId(id: string | undefined) {
  defaultOrganizationId = id;
}

let refreshPromise: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${apiBase}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": readCookie("csrf_token") ?? "" },
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshPromise = null), 0);
      });
  }
  return refreshPromise;
}

/**
 * May a 401 be fixed by renewing the sign-in? "token_expired": the short-lived token ran out. "unauthenticated" with
 * the CSRF cookie still present: the browser dropped the short-lived cookie (older sign-ins, or a browser cleaning
 * up) while the long sign-in is still valid. Visitors who never signed in have no CSRF cookie, so they cost nothing.
 */
function renewable(code: string | undefined, panel: boolean): boolean {
  if (code === "token_expired") return true;
  return code === "unauthenticated" && !panel && Boolean(readCookie("csrf_token"));
}

/** Renew the sign-in in use: the embedded panel's own, or the ordinary one (cookies). */
export function renewSession(): Promise<boolean> {
  return panelSession() ? refreshPanelSession() : tryRefresh();
}

/**
 * GET a private file (screenshot, document, export) with the session and organization header, renewing an expired
 * sign-in once, like every other request.
 */
export async function sessionFetch(url: string, organizationId?: string | null): Promise<Response> {
  const send = () => fetch(url, {
    credentials: credentialsMode(),
    headers: { ...(organizationId ? { "X-Organization-Id": organizationId } : {}), ...panelHeaders() },
  });
  const res = await send();
  if (res.status !== 401) return res;
  const body = (await res.clone().json().catch(() => null)) as { code?: string } | null;
  return renewable(body?.code, Boolean(panelSession())) && (await renewSession()) ? send() : res;
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}, _retried = false): Promise<T> {
  const { method = "GET", body, searchParams, headers, ...rest } = options;
  // Inside the clinic's app (embedded panel): the panel's own sign-in and always its clinic, never the cookies.
  const panel = panelSession();
  const organizationId = panel ? panel.organizationId : (options.organizationId ?? defaultOrganizationId);
  const origin =
    typeof window !== "undefined" ? window.location.origin : process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const url = new URL(`${apiBase}${path.startsWith("/") ? path : `/${path}`}`, origin);
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
  }

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) finalHeaders.set("Content-Type", "application/json");
  if (organizationId) finalHeaders.set("X-Organization-Id", organizationId);
  if (panel) finalHeaders.set("Authorization", `Bearer ${panel.access}`);
  if (method !== "GET") {
    const csrf = readCookie("csrf_token");
    if (csrf) finalHeaders.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(url, {
    ...rest,
    method,
    headers: finalHeaders,
    credentials: credentialsMode(),
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const json = text ? safeJson(text) : null;
  if (!response.ok) {
    const error = new ApiError(response.status, json as ApiErrorBody | null, response.statusText);
    const isAuthRoute = path.startsWith("/auth/");
    if (response.status === 401 && !isAuthRoute && !_retried && renewable(error.code, Boolean(panel))) {
      if (await (panel ? refreshPanelSession() : tryRefresh())) return apiRequest<T>(path, options, true);
    }
    // Sensitive action (reveal, export, document, settings): confirm it is still the same person, then try again.
    if (response.status === 403 && error.code === "reauth_required" && !_retried) {
      if (await askReauth()) return apiRequest<T>(path, options, true);
    }
    if (response.status === 403 && error.code === "session_locked") notifyLocked();
    // The clinic requires two-step sign-in for administrators and this account has not set it up yet.
    if (response.status === 403 && error.code === "mfa_setup_required" && !panel && typeof window !== "undefined" && !window.location.pathname.startsWith("/customer/profile")) {
      // Outside React (no router here); a full page load is fine for this one-off redirect.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/customer/profile?mfa=required#two-step");
    }
    throw error;
  }
  return json as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: "DELETE" }),
};
