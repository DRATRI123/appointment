import { NextResponse, type NextRequest } from "next/server";

/**
 * Content-Security-Policy with a fresh nonce per request. Only scripts carrying the nonce (Next.js adds it to its own
 * scripts) or loaded by them ('strict-dynamic') may run, so injected markup cannot execute script even if it
 * slipped past React's escaping. Styles keep 'unsafe-inline' (component libraries set inline styles; styles cannot
 * run code).
 */
export function buildCsp(nonce: string, { dev = false, apiOrigin = "" }: { dev?: boolean; apiOrigin?: string } = {}) {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: https:${apiOrigin ? ` ${apiOrigin}` : ""}`,
    "font-src 'self' data:",
    `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${dev ? " ws:" : ""}`,
    "frame-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

function apiOrigin() {
  try {
    return process.env.NEXT_PUBLIC_API_URL ? new URL(process.env.NEXT_PUBLIC_API_URL).origin : "";
  } catch {
    return "";
  }
}

export function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const csp = buildCsp(nonce, { dev: process.env.NODE_ENV !== "production", apiOrigin: apiOrigin() });
  // Next.js reads the nonce from the request's CSP header and stamps it on every script it renders.
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: proxied API/docs/media keep the backend's own CSP; static assets need none.
      source: "/((?!api/|_next/static|_next/image|favicon.ico|media/|docs|redoc).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
