import { describe, expect, it } from "vitest";
import { presetRange } from "@/components/analytics/filters-bar";
import { addDays, titleCase, toISODate } from "@/lib/format";

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
