"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { consent, doNotTrack, loadAnalytics, setConsent, trackEvent, type AnalyticsIds } from "@/lib/analytics";

/**
 * Asks once whether this visitor allows the clinic's analytics (Google Analytics / Tag Manager). Shown only when the
 * clinic switched analytics on, and never to browsers that ask not to be tracked.
 */
export function AnalyticsConsent({ slug, ids }: { slug: string; ids: AnalyticsIds | null | undefined }) {
  const pathname = usePathname();
  // The stored answer is read on the client only (the server renders nothing), without a second render pass.
  const stored = useSyncExternalStore(() => () => undefined, () => (doNotTrack() ? "hidden" : consent(slug)), () => "hidden" as const);
  const [answer, setAnswer] = useState<"granted" | "denied" | null>(null);
  const state = answer ?? stored;

  useEffect(() => {
    if (ids && state === "granted") loadAnalytics(slug, ids);
  }, [slug, ids, state]);

  useEffect(() => {
    if (state === "granted") trackEvent("page_view", { clinic: slug });
  }, [pathname, state, slug]);

  if (!ids || state !== null) return null;
  return (
    <div role="dialog" aria-live="polite" aria-label="Analytics" className="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-xl rounded-xl border bg-card p-4 text-sm shadow-lg"
      data-testid="analytics-consent">
      <p>This clinic would like to measure visits to improve its booking page (Google Analytics). No names, numbers or health details are shared.</p>
      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={() => { setConsent(slug, "denied"); setAnswer("denied"); }}>No, thanks</Button>
        <Button size="sm" onClick={() => { setConsent(slug, "granted"); setAnswer("granted"); }}>Allow</Button>
      </div>
    </div>
  );
}
