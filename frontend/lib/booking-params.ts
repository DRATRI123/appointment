/**
 * URL parameters for preselecting a service, branch or doctor on the public booking page, e.g.
 *   /akshar-clinic?service=consultation&branch=main&doctor=dr-mehta&date=2026-11-20
 *
 * They are only hints for the page. A value is used when it matches something the clinic actually offers (by slug or
 * id); anything else is ignored. They never affect price, availability or permissions: the server decides those.
 */

const TOKEN = /^[a-z0-9][a-z0-9-]{0,79}$/; // slugs; ids are UUIDs, which also match this shape
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export interface BookingParams {
  service?: string;
  branch?: string;
  doctor?: string;
  date?: string;
}

function clean(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const v = value.trim().toLowerCase();
  return TOKEN.test(v) ? v : undefined;
}

export function parseBookingParams(params: { get(name: string): string | null }): BookingParams {
  const date = params.get("date")?.trim();
  const validDate = date && DATE.test(date) && !Number.isNaN(Date.parse(`${date}T00:00:00Z`)) ? date : undefined;
  return {
    service: clean(params.get("service")),
    branch: clean(params.get("branch") ?? params.get("location")),
    doctor: clean(params.get("doctor") ?? params.get("professional")),
    date: validDate,
  };
}

/** Find the item a URL hint points to, by slug or id. Unknown hints resolve to nothing. */
export function matchHint<T extends { id: string; slug: string }>(items: readonly T[] | undefined, hint: string | undefined): T | undefined {
  if (!hint || !items) return undefined;
  return items.find((item) => item.slug.toLowerCase() === hint || item.id.toLowerCase() === hint);
}

/**
 * Build a shareable link (admin "Booking page" screen and Shopify instructions). `target` "book" goes straight to the
 * booking steps, "site" to the clinic website, "embed" to the frame page. Campaign labels (utm_*) are appended for
 * the website analytics; like the hints, they never affect price or permissions.
 */
export function bookingUrl(origin: string, slug: string, hints: BookingParams = {}, embed = false, campaign: Record<string, string> = {}, target: "book" | "site" = "book"): string {
  const path = embed ? `/embed/${encodeURIComponent(slug)}` : target === "site" ? `/${encodeURIComponent(slug)}` : `/${encodeURIComponent(slug)}/book`;
  const url = new URL(path, origin);
  for (const [key, value] of Object.entries(hints)) if (value) url.searchParams.set(key, value);
  for (const [key, value] of Object.entries(campaign)) if (value && /^[a-z0-9][a-z0-9._-]{0,63}$/.test(value)) url.searchParams.set(key, value);
  return url.toString();
}
