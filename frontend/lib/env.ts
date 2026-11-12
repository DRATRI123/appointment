/**
 * Public runtime configuration. Only NEXT_PUBLIC_* values are ever shipped to the browser.
 *
 * By default the API is reached on the same origin ("/api/v1") and Next.js proxies it to the backend
 * (see next.config.ts). Set NEXT_PUBLIC_API_URL to an absolute URL to bypass the proxy.
 */
export const env = {
  apiUrl: (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, ""),
  apiPrefix: process.env.NEXT_PUBLIC_API_PREFIX ?? "/api/v1",
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "Appointment Platform",
} as const;

export const apiBase = `${env.apiUrl}${env.apiPrefix}`;
