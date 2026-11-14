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
