import { describe, expect, it } from "vitest";
import { bookingUrl, matchHint, parseBookingParams } from "@/lib/booking-params";
import { contrast, safeHex, textOn } from "@/components/public-booking/brand";

const q = (s: string) => new URLSearchParams(s);

describe("booking URL parameters", () => {
  it("reads service, branch and doctor hints, with friendly aliases", () => {
    expect(parseBookingParams(q("service=Consultation&location=main&professional=dr-mehta&date=2026-11-20"))).toEqual({
      service: "consultation", branch: "main", doctor: "dr-mehta", date: "2026-11-20",
    });
  });

  it.each([
    ["script", "service=<script>alert(1)</script>"],
    ["path traversal", "service=../../admin"],
    ["url", "service=https://evil.example"],
    ["spaces", "branch=main branch"],
    ["too long", `doctor=${"a".repeat(81)}`],
    ["bad date", "date=2026-13-45"],
    ["date with time", "date=2026-11-20T10:00"],
  ])("ignores unsafe or malformed values (%s)", (_label, query) => {
    const parsed = parseBookingParams(q(query));
    expect(Object.values(parsed).filter(Boolean)).toEqual([]);
  });

  it("only matches things the clinic actually offers", () => {
    const services = [{ id: "3f1c2b6e-0000-4000-8000-000000000001", slug: "consultation" }, { id: "x2", slug: "panchakarma" }];
    expect(matchHint(services, "consultation")?.slug).toBe("consultation");
    expect(matchHint(services, "3f1c2b6e-0000-4000-8000-000000000001")?.slug).toBe("consultation");
    expect(matchHint(services, "surgery")).toBeUndefined();
    expect(matchHint(undefined, "consultation")).toBeUndefined();
  });

  it("builds shareable links and embed links", () => {
    expect(bookingUrl("https://booking.example.com", "akshar-clinic", { service: "consultation" }))
      .toBe("https://booking.example.com/akshar-clinic?service=consultation");
    expect(bookingUrl("https://booking.example.com", "akshar-clinic", { branch: "main" }, true))
      .toBe("https://booking.example.com/embed/akshar-clinic?branch=main");
  });
});

describe("brand colours", () => {
  it("falls back to the default when the setting is not a plain hex colour", () => {
    expect(safeHex("#0F766E")).toBe("#0f766e");
    expect(safeHex("red;background:url(x)")).toBe("#0f766e");
    expect(safeHex(undefined, "#123456")).toBe("#123456");
  });

  it("always picks readable text on the brand colour", () => {
    for (const brand of ["#0f766e", "#14b8a6", "#fde047", "#1e3a8a", "#ffffff", "#000000", "#e11d48"]) {
      expect(contrast(brand, textOn(brand))).toBeGreaterThanOrEqual(4.5);
    }
    expect(textOn("#fde047")).toBe("#111827");
    expect(textOn("#0f766e")).toBe("#ffffff");
  });
});
