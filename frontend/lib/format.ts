export function formatDateTime(value: string | null | undefined, timeZone?: string | null, locale = "en-IN") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: timeZone ?? undefined }).format(new Date(value));
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

/** "just now", "4 min ago", "3 h ago", "2 days ago"; "never" for missing values. */
export function timeAgo(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "never";
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(value).getTime()) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
