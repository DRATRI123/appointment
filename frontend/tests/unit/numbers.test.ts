import { describe, expect, it } from "vitest";
import { compactNumber, compactRupees, percent } from "@/lib/numbers";
import { formatPaise } from "@/lib/utils";

describe("money is stored and passed around in integer paise", () => {
  it("formats paise as rupees with two decimals", () => {
    expect(formatPaise(50000)).toBe("₹500.00");
    expect(formatPaise(1)).toBe("₹0.01");
    expect(formatPaise(12345678)).toBe("₹1,23,456.78");
  });

  it("uses Indian grouping and compact lakh notation for large figures", () => {
    expect(compactRupees(50000)).toBe("₹500");
    expect(compactRupees(9_999_900)).toBe("₹99,999");
    expect(compactRupees(12_000_000)).toBe("₹1.2L");
    expect(compactNumber(1284)).toBe("1,284");
    expect(compactNumber(129_000)).toBe("1.3L");
  });
});

describe("percent", () => {
  it("never shows a non-zero share as 0%", () => {
    expect(percent(0.004)).toBe("<1%");
    expect(percent(0)).toBe("0%");
    expect(percent(0.256, 1)).toBe("25.6%");
  });
  it("shows a dash when there is no data", () => {
    expect(percent(null)).toBe("—");
    expect(percent(undefined)).toBe("—");
  });
});
