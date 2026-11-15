/**
 * Cookie-free website counters: page views, Book clicks and booking-page views, by page and campaign source.
 * Nothing identifies the visitor; browsers asking not to be tracked (Do Not Track / Global Privacy Control) send nothing.
 */
import { env } from "@/lib/env";

type Metric = "page_view" | "book_click" | "booking_view";

function optedOut(): boolean {
  const n = navigator as Navigator & { globalPrivacyControl?: boolean };
  return n.doNotTrack === "1" || n.globalPrivacyControl === true;
}

export function sendSiteEvent(slug: string, metric: Metric, key: string, source = "") {
  if (typeof window === "undefined" || optedOut()) return;
  const url = `${env.apiUrl}${env.apiPrefix}/public/organizations/${encodeURIComponent(slug)}/events`;
  try {
    void fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ metric, key, source }), keepalive: true, credentials: "omit" }).catch(() => undefined);
  } catch {
    /* counting must never affect the page */
  }
}
