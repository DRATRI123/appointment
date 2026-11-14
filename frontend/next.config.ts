import type { NextConfig } from "next";

/**
 * The browser talks only to the Next.js origin. Requests to /api/* are proxied server-side to the
 * FastAPI backend (API_INTERNAL_URL), which removes CORS and cross-host cookie issues in both local
 * development and production. Set NEXT_PUBLIC_API_URL to call the backend directly instead.
 */
const apiInternalUrl = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const isDev = process.env.NODE_ENV !== "production";
const apiOrigin = (() => {
  try { return process.env.NEXT_PUBLIC_API_URL ? new URL(process.env.NEXT_PUBLIC_API_URL).origin : ""; } catch { return ""; }
})();

// Content Security Policy. Next.js hydration needs inline scripts; 'unsafe-eval' only in development (hot reload).
// Images may come from https (Google avatars, clinic logos hosted elsewhere) and data:/blob: (QR codes, previews).
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: https:${apiOrigin ? ` ${apiOrigin}` : ""}`,
  "font-src 'self' data:",
  `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${isDev ? " ws:" : ""}`,
  "frame-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  // Set ENABLE_HSTS=true once the site is served only over HTTPS.
  ...(process.env.ENABLE_HSTS === "true" ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    // Proxied API, docs and media responses keep the backend's own headers (two CSPs would intersect).
    return [{ source: "/((?!api/|docs|redoc|media/).*)", headers: securityHeaders }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` },
      { source: "/docs", destination: `${apiInternalUrl}/docs` },
      { source: "/redoc", destination: `${apiInternalUrl}/redoc` },
      // Public uploads (logos, photos, static UPI QR images) are served by the API.
      { source: "/media/:path*", destination: `${apiInternalUrl}/media/:path*` },
    ];
  },
};

export default nextConfig;
