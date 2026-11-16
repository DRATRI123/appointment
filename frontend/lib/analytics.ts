/**
 * Google Analytics 4 / Tag Manager for a clinic's public pages, only after the visitor agrees.
 *
 * - Nothing loads before consent (Consent Mode v2 defaults are "denied"; advertising storage stays denied).
 * - Browsers asking not to be tracked (Do Not Track / Global Privacy Control) never see the banner and never load it.
 * - Page addresses are cleaned: no query string (access tokens, campaign values) and no booking reference.
 * - Events carry the clinic and the campaign source only: never names, numbers, notes or the reason for the visit.
 */
export interface AnalyticsIds {
  ga4_measurement_id: string | null;
  gtm_container_id: string | null;
}

type Gtag = (...args: unknown[]) => void;
type W = Window & { dataLayer?: unknown[]; gtag?: Gtag; __apAnalytics?: string };

const KEY = (slug: string) => `ap.analytics.${slug}`;

export function doNotTrack(): boolean {
  if (typeof navigator === "undefined") return true;
  const n = navigator as Navigator & { globalPrivacyControl?: boolean };
  return n.doNotTrack === "1" || n.globalPrivacyControl === true;
}

export function consent(slug: string): "granted" | "denied" | null {
  try {
    const v = window.localStorage.getItem(KEY(slug));
    return v === "granted" || v === "denied" ? v : null;
  } catch {
    return null;
  }
}

export function setConsent(slug: string, value: "granted" | "denied") {
  try {
    window.localStorage.setItem(KEY(slug), value);
  } catch {
    /* private mode: ask again next time */
  }
}

/** "/clinic/appointments/APT-123?t=secret" → "/clinic/appointments/:reference" */
export function cleanPath(pathname: string): string {
  return pathname.replace(/\/appointments\/[^/]+/, "/appointments/:reference").slice(0, 200);
}

function inject(src: string) {
  const s = document.createElement("script");
  s.async = true;
  s.src = src;
  document.head.appendChild(s);
}

export function loadAnalytics(slug: string, ids: AnalyticsIds) {
  const w = window as W;
  if (w.__apAnalytics === slug || doNotTrack() || consent(slug) !== "granted") return;
  w.__apAnalytics = slug;
  w.dataLayer = w.dataLayer || [];
  const gtag: Gtag = function gtag() {
    // eslint-disable-next-line prefer-rest-params
    w.dataLayer!.push(arguments);
  };
  w.gtag = gtag;
  gtag("consent", "default", { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied", analytics_storage: "granted" });
  gtag("js", new Date());
  if (ids.ga4_measurement_id) {
    gtag("config", ids.ga4_measurement_id, { send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false });
    inject(`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ids.ga4_measurement_id)}`);
  }
  if (ids.gtm_container_id) {
    w.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    inject(`https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(ids.gtm_container_id)}`);
  }
}

/** booking_start, booking_complete, booking_abandoned, page_view. Safe to call when analytics is off (does nothing). */
export function trackEvent(name: "page_view" | "booking_start" | "booking_complete" | "booking_abandoned", params: { clinic: string; source?: string }) {
  const w = typeof window === "undefined" ? undefined : (window as W);
  if (!w?.gtag || !w.__apAnalytics) return;
  const page = { page_location: `${window.location.origin}${cleanPath(window.location.pathname)}`, page_path: cleanPath(window.location.pathname) };
  w.gtag("event", name, { ...page, clinic: params.clinic, booking_source: (params.source || "direct").slice(0, 40) });
}
