import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api-client";
import { askReauth, setLockHandler, setReauthHandler } from "@/lib/privacy-bus";
import { isMasked } from "@/components/privacy/masked-contact";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  setReauthHandler(null);
  setLockHandler(null);
  vi.unstubAllGlobals();
});

describe("confirm it is you", () => {
  it("asks once, then retries the request that needed it", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(403, { detail: "Please confirm it is you before you continue.", code: "reauth_required" }))
      .mockResolvedValueOnce(json(200, { mobile: "+919811111111" }));
    vi.stubGlobal("fetch", fetchMock);
    const handler = vi.fn().mockResolvedValue(true);
    setReauthHandler(handler);
    await expect(api.post("/customers/c1/reveal", {})).resolves.toEqual({ mobile: "+919811111111" });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry when the person cancels", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(403, { detail: "Please confirm it is you before you continue.", code: "reauth_required" }));
    vi.stubGlobal("fetch", fetchMock);
    setReauthHandler(() => Promise.resolve(false));
    await expect(api.post("/customers/c1/reveal", {})).rejects.toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shares one dialog between requests made at the same time", async () => {
    let resolve!: (ok: boolean) => void;
    const handler = vi.fn(() => new Promise<boolean>((r) => (resolve = r)));
    setReauthHandler(handler);
    const a = askReauth();
    const b = askReauth();
    resolve(true);
    await expect(Promise.all([a, b])).resolves.toEqual([true, true]);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("without a dialog on the page (patient area), nothing is asked", async () => {
    await expect(askReauth()).resolves.toBe(false);
  });
});

describe("screen lock", () => {
  it("a locked session shows the lock screen", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(403, { detail: "Screen locked.", code: "session_locked" })));
    const onLock = vi.fn();
    setLockHandler(onLock);
    await expect(api.get("/customers")).rejects.toBeTruthy();
    expect(onLock).toHaveBeenCalledTimes(1);
  });
});

describe("masked values", () => {
  it("recognises hidden mobile numbers and emails", () => {
    expect(isMasked("+9198111XXXXX")).toBe(true);
    expect(isMasked("atr***@example.com")).toBe(true);
    expect(isMasked("+919811111111")).toBe(false);
    expect(isMasked("asha@example.com")).toBe(false);
    expect(isMasked(null)).toBe(false);
  });
});
