/** Clinic brand colour helpers. The brand colour tints the hero; text on it is chosen for contrast automatically. */

const HEX = /^#([0-9a-f]{6})$/i;

export function safeHex(value: unknown, fallback = "#0f766e"): string {
  return typeof value === "string" && HEX.test(value.trim()) ? value.trim().toLowerCase() : fallback;
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const n = parseInt(safeHex(hex).slice(1), 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

export function contrast(a: string, b: string): number {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** White or near-black, whichever reads better on the brand colour (WCAG contrast). */
export function textOn(hex: string): "#ffffff" | "#111827" {
  return contrast(hex, "#ffffff") >= contrast(hex, "#111827") ? "#ffffff" : "#111827";
}
