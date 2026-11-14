import type { NextConfig } from "next";

/**
 * The browser talks only to the Next.js origin. Requests to /api/* are proxied server-side to the
 * FastAPI backend (API_INTERNAL_URL), which removes CORS and cross-host cookie issues in both local
 * development and production. Set NEXT_PUBLIC_API_URL to call the backend directly instead.
 */
const apiInternalUrl = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// Content-Security-Policy is set per request with a nonce in proxy.ts.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  // Set ENABLE_HSTS=true once the site is served only over HTTPS.
  ...(process.env.ENABLE_HSTS === "true" ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  // The Docker image sets NEXT_OUTPUT=standalone: a self-contained server.js with only the files it needs.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
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
