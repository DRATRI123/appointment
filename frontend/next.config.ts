import type { NextConfig } from "next";

/**
 * The browser talks only to the Next.js origin. Requests to /api/* are proxied server-side to the
 * FastAPI backend (API_INTERNAL_URL), which removes CORS and cross-host cookie issues in both local
 * development and production. Set NEXT_PUBLIC_API_URL to call the backend directly instead.
 */
const apiInternalUrl = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
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
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` },
      { source: "/docs", destination: `${apiInternalUrl}/docs` },
      { source: "/redoc", destination: `${apiInternalUrl}/redoc` },
    ];
  },
};

export default nextConfig;
