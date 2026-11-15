import { describe, expect, it } from "vitest";
import { presetRange } from "@/components/analytics/filters-bar";
import { addDays, timeAgo, titleCase, toISODate } from "@/lib/format";

const now = new Date(2026, 2, 15, 10, 30); // 15 March 2026, local time

describe("analytics date presets", () => {
  it("covers inclusive day counts ending today", () => {
    expect(presetRange("today", now)).toEqual({ from: "2026-03-15", to: "2026-03-15" });
    expect(presetRange("7d", now)).toEqual({ from: "2026-03-09", to: "2026-03-15" });
    expect(presetRange("30d", now)).toEqual({ from: "2026-02-14", to: "2026-03-15" });
    expect(presetRange("90d", now)).toEqual({ from: "2025-12-16", to: "2026-03-15" });
  });

  it("handles calendar months, including year boundaries", () => {
    expect(presetRange("month", now)).toEqual({ from: "2026-03-01", to: "2026-03-15" });
    expect(presetRange("last_month", now)).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(presetRange("last_month", new Date(2026, 0, 5))).toEqual({ from: "2025-12-01", to: "2025-12-31" });
  });
});

describe("date helpers", () => {
  it("formats local dates without shifting to UTC", () => {
    expect(toISODate(new Date(2026, 10, 14, 0, 15))).toBe("2026-11-14");
    expect(toISODate(addDays(new Date(2026, 1, 28), 1))).toBe("2026-03-01");
  });
  it("title-cases enum values", () => {
    expect(titleCase("under_review")).toBe("Under Review");
    expect(titleCase("no-show")).toBe("No Show");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-11-14T12:00:00Z");
  it("reads naturally at every scale", () => {
    expect(timeAgo(null, now)).toBe("never");
    expect(timeAgo("2026-11-14T11:59:30Z", now)).toBe("just now");
    expect(timeAgo("2026-11-14T11:56:00Z", now)).toBe("4 min ago");
    expect(timeAgo("2026-11-14T09:00:00Z", now)).toBe("3 h ago");
    expect(timeAgo("2026-11-13T12:00:00Z", now)).toBe("24 h ago");
    expect(timeAgo("2026-11-12T12:00:00Z", now)).toBe("2 days ago");
    expect(timeAgo("2026-11-14T12:05:00Z", now)).toBe("just now"); // clock skew never shows negative times
  });
});

describe("presetRange in the clinic's time zone", () => {
  it("uses the clinic's date, not the browser's", () => {
    // 20:00 UTC on 15 Nov is already 16 Nov (01:30) in India
    const now = new Date(Date.UTC(2026, 10, 15, 20, 0));
    expect(presetRange("today", now, "Asia/Kolkata")).toEqual({ from: "2026-11-16", to: "2026-11-16" });
    expect(presetRange("30d", now, "Asia/Kolkata").to).toBe("2026-11-16");
    expect(presetRange("today", now, "America/New_York")).toEqual({ from: "2026-11-15", to: "2026-11-15" });
  });

  it("falls back to the browser's date for an unknown zone", () => {
    const now = new Date(2026, 2, 15, 10);
    expect(presetRange("today", now, "Not/AZone")).toEqual({ from: "2026-03-15", to: "2026-03-15" });
  });
});
