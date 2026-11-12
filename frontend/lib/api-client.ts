/**
 * Centralised API client.
 *
 * - Sends cookies (HttpOnly auth cookies are set by the backend in Phase 2).
 * - Attaches the CSRF token header for unsafe methods when the cookie is present.
 * - Normalises backend error envelopes into `ApiError`.
 */
import { apiBase } from "@/lib/env";
import type { ApiErrorBody } from "@/types/api";

export class ApiError extends Error {
  status: number;
  code: string;
  errors?: unknown;
  requestId?: string;

  constructor(status: number, body: ApiErrorBody | null, fallback = "Request failed") {
    super(body?.detail ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? "unknown_error";
    this.errors = body?.errors;
    this.requestId = body?.request_id;
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

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, organizationId, searchParams, headers, ...rest } = options;
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
  if (method !== "GET") {
    const csrf = readCookie("csrf_token");
    if (csrf) finalHeaders.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(url, {
    ...rest,
    method,
    headers: finalHeaders,
    credentials: "include",
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const json = text ? safeJson(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, json as ApiErrorBody | null, response.statusText);
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
