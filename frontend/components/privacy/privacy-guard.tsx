"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { setLockHandler, setReauthHandler } from "@/lib/privacy-bus";
import { privacyService, type PrivacyPolicy } from "@/services/privacy";
import { ReauthForm } from "./reauth-form";
import { Watermark } from "./watermark";

const ACTIVITY = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"] as const;

/**
 * Privacy for staff screens (clinic privacy settings; the API enforces the same rules):
 * - locks after inactivity (per role), and optionally when the tab is hidden; while locked the page content is removed
 *   from the screen and the API refuses every request until the person confirms it is them;
 * - asks "confirm it is you" when the API needs it (reveal, export, documents, sensitive settings) and retries;
 * - shows a watermark with an account reference, the time and the session (no personal data);
 * - records print attempts and shows a confidentiality notice, or blocks printing if the clinic chose that.
 * A browser cannot stop screenshots, screen recording or a phone camera: these are deterrents and a trail.
 */
export function PrivacyGuard({ enabled, children }: { enabled: boolean; children: React.ReactNode }) {
  const { currentOrganizationId, logout } = useAuth();
  const queryClient = useQueryClient();
  const policyQuery = useQuery({
    queryKey: ["privacy-policy", currentOrganizationId],
    queryFn: privacyService.policy,
    enabled: enabled && !!currentOrganizationId,
    staleTime: 60_000,
    retry: false,
  });
  const policy = enabled ? policyQuery.data : undefined;
  const [locked, setLocked] = useState(false);
  const [reauth, setReauth] = useState<((ok: boolean) => void) | null>(null);
  const lastActivity = useRef(0);

  const lockNow = useCallback(() => {
    setLocked(true);
    privacyService.lock().catch(() => undefined);
  }, []);

  // The API client calls these (outside React).
  useEffect(() => {
    if (!enabled) return;
    setReauthHandler(() => new Promise<boolean>((resolve) => setReauth(() => resolve)));
    setLockHandler(() => setLocked(true));
    return () => {
      setReauthHandler(null);
      setLockHandler(null);
    };
  }, [enabled]);

  // Inactivity lock.
  useEffect(() => {
    if (!policy) return;
    lastActivity.current = Date.now();
    const bump = () => (lastActivity.current = Date.now());
    ACTIVITY.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const limit = policy.lock_after_minutes * 60_000;
    const timer = window.setInterval(() => {
      if (Date.now() - lastActivity.current > limit) lockNow();
    }, 5_000);
    const onVisibility = () => {
      if (policy.lock_when_hidden && document.visibilityState === "hidden") lockNow();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      ACTIVITY.forEach((e) => window.removeEventListener(e, bump));
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [policy, lockNow]);

  // Printing: recorded; warned or blocked by clinic policy (CSS in globals.css uses data-print-policy).
  useEffect(() => {
    if (!policy) return;
    const root = document.documentElement;
    root.dataset.printPolicy = policy.print_policy;
    const before = () => {
      privacyService.printAttempt(window.location.pathname).catch(() => undefined);
      if (policy.print_policy === "warn") toast.warning("This printout contains confidential patient information. Printing is recorded.");
    };
    window.addEventListener("beforeprint", before);
    return () => {
      window.removeEventListener("beforeprint", before);
      delete root.dataset.printPolicy;
    };
  }, [policy]);

  if (!enabled) return <>{children}</>;

  if (locked) {
    return (
      <LockScreen
        policy={policy}
        onUnlocked={() => {
          setLocked(false);
          lastActivity.current = Date.now();
          queryClient.invalidateQueries();
        }}
        onSignOut={() => void logout()}
      />
    );
  }

  return (
    <>
      {children}
      <p className="print-only-notice text-sm">Printing is turned off for this clinic. The attempt was recorded.</p>
      <p className="mt-10 flex items-center gap-1.5 text-xs text-muted-foreground print-confidential" data-testid="confidential-notice">
        <ShieldCheck className="size-3.5" aria-hidden /> Confidential: patient information. Opening records, revealing details and exports are recorded
        {policy ? ` (${policy.user_ref}).` : "."}
      </p>
      {policy?.watermark_enabled ? <Watermark policy={policy} /> : null}
      <Dialog open={!!reauth} onOpenChange={(open) => { if (!open && reauth) { reauth(false); setReauth(null); } }}>
        <DialogContent data-testid="reauth-dialog">
          <DialogHeader>
            <DialogTitle>Confirm it is you</DialogTitle>
            <DialogDescription>
              This shows or exports sensitive patient information. Confirm once and you will not be asked again for {policy?.reauth_window_minutes ?? 10} minutes.
            </DialogDescription>
          </DialogHeader>
          <ReauthForm policy={policy} onDone={() => { reauth?.(true); setReauth(null); }} />
        </DialogContent>
      </Dialog>
    </>
  );
}

function LockScreen({ policy, onUnlocked, onSignOut }: { policy?: PrivacyPolicy; onUnlocked: () => void; onSignOut: () => void }) {
  return (
    <section className="mx-auto mt-10 max-w-md rounded-xl border bg-card p-6 shadow-sm" role="dialog" aria-modal="true" aria-labelledby="lock-title" data-testid="lock-screen">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Lock className="size-5" aria-hidden /></span>
        <div>
          <h2 id="lock-title" className="text-lg font-semibold">Screen locked</h2>
          <p className="text-sm text-muted-foreground">Locked after a period without use, to protect patient information.</p>
        </div>
      </div>
      <ReauthForm policy={policy} onDone={onUnlocked} submitLabel="Unlock" />
      <Button variant="link" className="mt-3 px-0" onClick={onSignOut}>Sign out instead</Button>
    </section>
  );
}
