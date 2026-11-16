import { NextResponse, type NextRequest } from "next/server";

/**
 * Content-Security-Policy with a fresh nonce per request. Only scripts carrying the nonce (Next.js adds it to its own
 * scripts) or loaded by them ('strict-dynamic') may run, so injected markup cannot execute script even if it
 * slipped past React's escaping. Styles keep 'unsafe-inline' (component libraries set inline styles; styles cannot
 * run code).
 */
const GOOGLE_SIGN_IN = "https://accounts.google.com/gsi/";
const ANALYTICS = "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com";

export function buildCsp(
  nonce: string,
  { dev = false, apiOrigin = "", frameAncestors = [], selfFrame = false, googleSignIn = false, analytics = false }:
    { dev?: boolean; apiOrigin?: string; frameAncestors?: string[]; selfFrame?: boolean; googleSignIn?: boolean; analytics?: boolean } = {},
) {
  // Scripts: only this request's nonce (strict-dynamic lets those scripts load Google's sign-in or analytics library).
  // Google's sign-in button and analytics also need their own origins for frames, styles and requests, on the pages
  // that use them only: sign-in pages, and public clinic pages (never staff screens).
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'unsafe-inline'${googleSignIn ? ` ${GOOGLE_SIGN_IN}style` : ""}`,
    `img-src 'self' data: blob: https:${apiOrigin ? ` ${apiOrigin}` : ""}`,
    "font-src 'self' data:",
    `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${googleSignIn ? ` ${GOOGLE_SIGN_IN}` : ""}${analytics ? ` ${ANALYTICS}` : ""}${dev ? " ws:" : ""}`,
    `frame-src 'self'${googleSignIn ? ` ${GOOGLE_SIGN_IN}` : ""}`,
    // Only /embed/<clinic> pages may be framed, and only by the websites that clinic listed (plus this site itself).
    frameAncestors.length ? `frame-ancestors 'self' ${frameAncestors.join(" ")}` : selfFrame ? "frame-ancestors 'self'" : "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

const SIGN_IN_PATH = /^\/(login|register)(\/|$)/;
const STAFF_PATH = /^\/(admin|super-admin|professional|customer|onboarding|website-preview)(\/|$)/;

function apiOrigin() {
  try {
    return process.env.NEXT_PUBLIC_API_URL ? new URL(process.env.NEXT_PUBLIC_API_URL).origin : "";
  } catch {
    return "";
  }
}

const ORIGIN = /^https?:\/\/[a-z0-9.-]+(:\d{1,5})?$/;
const EMBED_PATH = /^\/embed\/([a-z0-9][a-z0-9-]{0,79})(?:\/|$)/;
const policyCache = new Map<string, { origins: string[]; at: number }>();
const FRESH_MS = 60_000;
const STALE_MS = 10 * 60_000;

/** Websites this clinic allows to show its booking page in an iframe (fail closed: none if unknown). */
export async function embedOrigins(slug: string, fetcher: typeof fetch = fetch, now = Date.now()): Promise<string[]> {
  const cached = policyCache.get(slug);
  if (cached && now - cached.at < FRESH_MS) return cached.origins;
  const api = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const r = await fetcher(`${api}/api/v1/public/organizations/${slug}/embed-policy`, { signal: AbortSignal.timeout(2000), cache: "no-store" });
    if (r.status === 404) {
      policyCache.set(slug, { origins: [], at: now });
      return [];
    }
    if (!r.ok) throw new Error(`embed policy ${r.status}`);
    const body = (await r.json()) as { allowed_origins?: unknown };
    // Re-validate: anything that is not a bare origin must never reach the header.
    const origins = Array.isArray(body.allowed_origins) ? body.allowed_origins.filter((o): o is string => typeof o === "string" && ORIGIN.test(o)) : [];
    policyCache.set(slug, { origins, at: now });
    return origins;
  } catch {
    // API briefly unreachable: keep the last known list for a while, otherwise refuse framing.
    return cached && now - cached.at < STALE_MS ? cached.origins : [];
  }
}

export function clearEmbedPolicyCache() {
  policyCache.clear();
}

export async function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const embed = EMBED_PATH.exec(request.nextUrl.pathname);
  const frameAncestors = embed ? await embedOrigins(embed[1]) : [];
  // The admin's live website preview frames /website-preview from this same site, and nothing else may.
  const preview = request.nextUrl.pathname === "/website-preview";
  const path = request.nextUrl.pathname;
  const csp = buildCsp(nonce, {
    dev: process.env.NODE_ENV !== "production", apiOrigin: apiOrigin(), frameAncestors, selfFrame: preview,
    googleSignIn: SIGN_IN_PATH.test(path), analytics: !STAFF_PATH.test(path) && !SIGN_IN_PATH.test(path),
  });
  // Next.js reads the nonce from the request's CSP header and stamps it on every script it renders.
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  // Old browsers ignore frame-ancestors; X-Frame-Options keeps every non-embed page out of frames for them too.
  if (!embed) response.headers.set("X-Frame-Options", preview ? "SAMEORIGIN" : "DENY");
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
