/**
 * Turn website buttons and menu items into addresses. The server already validated every target; this file decides
 * the final href so a stored value can never become a `javascript:` or other unexpected link.
 */
import type { NavItem, SiteButton, SiteSettings } from "@/types/website";

export interface LinkContext {
  base: string; // "/akshar-clinic"
  settings: Pick<SiteSettings, "phone" | "whatsapp" | "address" | "clinic_name">;
  /** Address used for "Directions" when a button names a location. */
  branchAddress?: (slug: string) => string | undefined;
  /** Id of the contact / services sections on the home page, for in-page links. */
  sectionIds?: { contact?: string; services?: string };
  /** Campaign parameters to carry into the booking page (utm_*, ref). */
  campaign?: Record<string, string>;
}

export interface ResolvedLink { href: string; external: boolean; newTab: boolean }

const SAFE_ABSOLUTE = /^https:\/\/[^\s"'<>]+$/i;
const SLUG = /^[a-z0-9][a-z0-9-]{0,79}$/;

export function phoneDigits(raw: string): string {
  const digits = raw.replace(/[^\d+]/g, "");
  return digits.startsWith("+") ? `+${digits.slice(1).replace(/\+/g, "")}` : digits;
}

/** wa.me wants the number in international format without "+"; Indian 10-digit numbers get 91 in front. */
export function whatsappNumber(raw: string): string {
  const d = phoneDigits(raw).replace(/^\+/, "");
  return /^[6-9]\d{9}$/.test(d) ? `91${d}` : d;
}

export function whatsappLink(number: string, message = ""): string {
  const n = whatsappNumber(number);
  return `https://wa.me/${n}${message ? `?text=${encodeURIComponent(message)}` : ""}`;
}

export function mapsLink(query: string): string {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function safeExternal(url: string): string | null {
  if (url.startsWith("/media/") && !url.includes("..")) return url;
  return SAFE_ABSOLUTE.test(url) ? url : null;
}

export function bookHref(base: string, hints: { service?: string; branch?: string; doctor?: string } = {}, campaign: Record<string, string> = {}): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(hints)) if (v && SLUG.test(v)) q.set(k, v);
  for (const [k, v] of Object.entries(campaign)) if (v) q.set(k, v);
  const qs = q.toString();
  return `${base}/book${qs ? `?${qs}` : ""}`;
}

/** Returns null when the button cannot work (e.g. "Call" without any phone number): the caller hides it. */
export function buttonHref(b: SiteButton, ctx: LinkContext): ResolvedLink | null {
  const internal = (href: string): ResolvedLink => ({ href, external: false, newTab: b.new_tab });
  switch (b.kind) {
    case "book":
      return internal(bookHref(ctx.base, { service: b.service, branch: b.branch }, ctx.campaign));
    case "call": {
      const phone = phoneDigits(b.phone || ctx.settings.phone);
      return phone.replace("+", "").length >= 6 ? { href: `tel:${phone}`, external: false, newTab: false } : null;
    }
    case "whatsapp": {
      const number = b.phone || ctx.settings.whatsapp;
      return whatsappNumber(number).length >= 8 ? { href: whatsappLink(number, b.message), external: true, newTab: true } : null;
    }
    case "contact":
      return internal(`${ctx.base}#${ctx.sectionIds?.contact ?? "contact"}`);
    case "services":
      return internal(`${ctx.base}#${ctx.sectionIds?.services ?? "services"}`);
    case "page":
      return SLUG.test(b.page) ? internal(`${ctx.base}/${b.page}`) : null;
    case "maps": {
      if (b.url) {
        const url = safeExternal(b.url);
        return url ? { href: url, external: true, newTab: true } : null;
      }
      const address = (b.branch && ctx.branchAddress?.(b.branch)) || ctx.settings.address;
      return address ? { href: mapsLink(`${ctx.settings.clinic_name} ${address}`), external: true, newTab: true } : null;
    }
    case "pdf":
    case "external":
    case "url": {
      const url = safeExternal(b.url);
      if (!url) return null;
      return { href: url, external: !url.startsWith("/"), newTab: b.kind !== "url" || b.new_tab };
    }
    default:
      return null;
  }
}

export function navHref(item: NavItem, base: string, campaign: Record<string, string> = {}): ResolvedLink | null {
  switch (item.kind) {
    case "book":
      return { href: bookHref(base, {}, campaign), external: false, newTab: false };
    case "section":
      return /^[a-z0-9][a-z0-9-]{0,39}$/.test(item.target) ? { href: `${base}#${item.target}`, external: false, newTab: false } : null;
    case "page":
      return SLUG.test(item.target) ? { href: `${base}/${item.target}`, external: false, newTab: item.new_tab } : null;
    case "url": {
      const url = SAFE_ABSOLUTE.test(item.target) ? item.target : null;
      return url ? { href: url, external: true, newTab: item.new_tab } : null;
    }
    default:
      return null;
  }
}

/** utm_* and ref from the visitor's address, cleaned, so a campaign can be carried into the booking page. */
export const CAMPAIGN_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref"] as const;

export function campaignParams(params: { get(name: string): string | null }): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of CAMPAIGN_KEYS) {
    const v = params.get(key)?.trim().toLowerCase();
    if (v && /^[a-z0-9][a-z0-9._-]{0,63}$/.test(v)) out[key] = v;
  }
  return out;
}
