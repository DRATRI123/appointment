/** Remembers campaign parameters (utm_*, ref) for the visit, so a booking made a few pages later is still attributed. */
import { campaignParams } from "@/lib/site-links";

const KEY = "ap.campaign";

export function rememberCampaign(params: { get(name: string): string | null }): Record<string, string> {
  const fresh = campaignParams(params);
  try {
    if (Object.keys(fresh).length) window.sessionStorage.setItem(KEY, JSON.stringify(fresh));
    const stored = JSON.parse(window.sessionStorage.getItem(KEY) ?? "{}") as Record<string, string>;
    return campaignParams({ get: (k) => (typeof stored[k] === "string" ? stored[k] : null) });
  } catch {
    return fresh; // storage blocked: use what is in the address
  }
}
