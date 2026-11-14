const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-IN");

/** 1,284 / 12.9K / 1.2L — Indian compact notation for big standalone figures. */
export function compactNumber(n: number) {
  return Math.abs(n) < 10_000 ? whole.format(n) : compact.format(n);
}

export function compactRupees(paise: number) {
  const r = paise / 100;
  return `₹${Math.abs(r) < 100_000 ? whole.format(Math.round(r)) : compact.format(r)}`;
}

export function percent(ratio: number | null | undefined, digits = 0) {
  if (ratio === null || ratio === undefined) return "—";
  if (ratio > 0 && ratio * 100 < 1 && digits === 0) return "<1%"; // never show a non-zero share as 0%
  return `${(ratio * 100).toFixed(digits)}%`;
}
