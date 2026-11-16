import { describe, expect, it } from "vitest";
import { buildCsp } from "@/proxy";

const directive = (csp: string, name: string) => csp.split("; ").find((d) => d.startsWith(name + " ")) ?? "";

describe("Content-Security-Policy", () => {
  it("only lets scripts with this request's nonce run, never inline script", () => {
    const script = directive(buildCsp("abc123"), "script-src");
    expect(script).toContain("'nonce-abc123'");
    expect(script).toContain("'strict-dynamic'");
    expect(script).not.toContain("'unsafe-inline'");
    expect(script).not.toContain("'unsafe-eval'");
  });
  it("blocks framing, plugins, foreign forms and base-tag hijacking", () => {
    const csp = buildCsp("n");
    for (const d of ["frame-ancestors 'none'", "object-src 'none'", "form-action 'self'", "base-uri 'self'"]) expect(csp).toContain(d);
  });
  it("allows eval and websockets only in development (hot reload)", () => {
    expect(directive(buildCsp("n", { dev: true }), "script-src")).toContain("'unsafe-eval'");
    expect(directive(buildCsp("n", { dev: true }), "connect-src")).toContain("ws:");
    expect(directive(buildCsp("n", { apiOrigin: "https://api.example.com" }), "connect-src")).toBe("connect-src 'self' https://api.example.com");
  });
});

describe("embedding (frame-ancestors)", () => {
  it("is refused everywhere unless a clinic lists its websites", () => {
    expect(directive(buildCsp("n"), "frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(directive(buildCsp("n", { frameAncestors: ["https://akshar.myshopify.com"] }), "frame-ancestors")).toBe("frame-ancestors 'self' https://akshar.myshopify.com");
  });
});

import { clearEmbedPolicyCache, embedOrigins } from "@/proxy";

function fakeFetch(status: number, body: unknown, calls: string[] = []) {
  return (async (url: RequestInfo | URL) => {
    calls.push(String(url));
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

describe("embedOrigins", () => {
  it("returns the clinic's allowed websites and caches them for a minute", async () => {
    clearEmbedPolicyCache();
    const calls: string[] = [];
    const f = fakeFetch(200, { allowed_origins: ["https://akshar.myshopify.com", "https://www.aksharclinic.com"] }, calls);
    expect(await embedOrigins("akshar-clinic", f, 1_000)).toEqual(["https://akshar.myshopify.com", "https://www.aksharclinic.com"]);
    await embedOrigins("akshar-clinic", f, 30_000);
    expect(calls).toHaveLength(1);
    await embedOrigins("akshar-clinic", f, 70_000);
    expect(calls).toHaveLength(2);
    expect(calls[0]).toContain("/api/v1/public/organizations/akshar-clinic/embed-policy");
  });

  it("drops anything that is not a bare origin, so it can never inject into the header", async () => {
    clearEmbedPolicyCache();
    const f = fakeFetch(200, { allowed_origins: ["https://ok.example.com", "https://x.com; script-src *", "https://a.com/path", "*", 42] });
    expect(await embedOrigins("c1", f, 0)).toEqual(["https://ok.example.com"]);
  });

  it("fails closed for unknown clinics and when the API is down (after the last good answer goes stale)", async () => {
    clearEmbedPolicyCache();
    expect(await embedOrigins("nope", fakeFetch(404, { detail: "Not found" }), 0)).toEqual([]);
    const ok = fakeFetch(200, { allowed_origins: ["https://shop.example.com"] });
    const down = (async () => { throw new Error("connection refused"); }) as typeof fetch;
    await embedOrigins("c2", ok, 0);
    expect(await embedOrigins("c2", down, 120_000)).toEqual(["https://shop.example.com"]); // brief outage: last known list
    expect(await embedOrigins("c2", down, 11 * 60_000)).toEqual([]); // long outage: refuse framing
    expect(await embedOrigins("c3", down, 0)).toEqual([]);
  });
});

describe("Google sign-in and analytics", () => {
  it("are allowed only where they are used", () => {
    const plain = buildCsp("n");
    expect(plain).not.toContain("accounts.google.com");
    expect(plain).not.toContain("google-analytics");
    const signIn = buildCsp("n", { googleSignIn: true });
    expect(directive(signIn, "frame-src")).toBe("frame-src 'self' https://accounts.google.com/gsi/");
    expect(directive(signIn, "connect-src")).toContain("https://accounts.google.com/gsi/");
    expect(directive(buildCsp("n", { analytics: true }), "connect-src")).toContain("https://*.google-analytics.com");
    // Scripts stay nonce-only in every case.
    expect(directive(signIn, "script-src")).not.toContain("accounts.google.com");
  });
});
