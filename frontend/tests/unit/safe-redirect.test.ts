import { describe, expect, it } from "vitest";
import { safeNextPath } from "@/lib/safe-redirect";

describe("safeNextPath (post-login open-redirect guard)", () => {
  it("keeps same-site paths with query and hash", () => {
    expect(safeNextPath("/admin/appointments?status=booked#top")).toBe("/admin/appointments?status=booked#top");
    expect(safeNextPath(encodeURIComponent("/o/sunrise/book?service=abc"))).toBe("/o/sunrise/book?service=abc");
  });

  it.each([
    ["empty", ""],
    ["missing", null],
    ["absolute URL", "https://evil.example/phish"],
    ["protocol-relative", "//evil.example"],
    ["encoded protocol-relative", "%2F%2Fevil.example"],
    ["backslash host", "/\\evil.example"],
    ["encoded backslash host", "%2F%5Cevil.example"],
    ["javascript scheme", "javascript:alert(1)"],
    ["relative path", "admin"],
    ["embedded backslash", "/admin\\..\\evil"],
    ["newline injection", "/admin%0d%0aSet-Cookie:x"],
    ["tab", "/\t/evil.example"],
    ["malformed encoding", "/%E0%A4%A"],
  ])("rejects %s", (_label, value) => {
    expect(safeNextPath(value)).toBeNull();
  });
});
