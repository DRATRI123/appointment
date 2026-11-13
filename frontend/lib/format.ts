export function formatDateTime(value: string | null | undefined, locale = "en-IN") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function titleCase(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatTime(value: string, timeZone?: string, locale = "en-IN") {
  return new Intl.DateTimeFormat(locale, { timeStyle: "short", timeZone }).format(new Date(value));
}

export function formatDate(value: string | Date, timeZone?: string, locale = "en-IN") {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone }).format(typeof value === "string" ? new Date(value) : value);
}

export function formatDateLong(value: string | Date, timeZone?: string, locale = "en-IN") {
  return new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone }).format(typeof value === "string" ? new Date(value) : value);
}

/** YYYY-MM-DD for a Date in local time. */
export function toISODate(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(d: Date, n: number) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}
