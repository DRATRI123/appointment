"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";
import { authService } from "@/services/auth";

type GoogleId = {
  accounts: {
    id: {
      initialize: (opts: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: string; context?: string }) => void;
      renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
    };
  };
};

let loading: Promise<void> | null = null;

function loadGoogle(): Promise<void> {
  if ((window as unknown as { google?: GoogleId }).google?.accounts?.id) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => { loading = null; reject(new Error("Google sign-in could not load")); };
    document.head.appendChild(s);
  });
  return loading;
}

/**
 * "Sign in with Google" (Google Identity Services). Shown only when the platform has a Google client ID (Super admin →
 * Integrations → Google, or .env). The ID token is checked on the server (signature, audience, issuer, verified email);
 * two-step sign-in still applies afterwards.
 */
export function GoogleSignIn({ onSuccess, onSecondStep, context = "signin" }: { onSuccess: () => Promise<void>; onSecondStep: (e: unknown) => boolean; context?: "signin" | "signup" }) {
  const config = useQuery({ queryKey: ["google-config"], queryFn: () => api.get<{ client_id: string | null }>("/auth/google/config"), staleTime: 300_000, retry: false });
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const clientId = config.data?.client_id;
  const handlers = useRef({ onSuccess, onSecondStep });
  useEffect(() => {
    handlers.current = { onSuccess, onSecondStep };
  }, [onSuccess, onSecondStep]);

  useEffect(() => {
    if (!clientId || !ref.current) return;
    let cancelled = false;
    loadGoogle().then(() => {
      if (cancelled || !ref.current) return;
      const g = (window as unknown as { google: GoogleId }).google;
      g.accounts.id.initialize({
        client_id: clientId,
        context,
        callback: async ({ credential }) => {
          try {
            await authService.google(credential);
            await handlers.current.onSuccess();
          } catch (e) {
            if (!handlers.current.onSecondStep(e)) toast.error(errorMessage(e));
          }
        },
      });
      g.accounts.id.renderButton(ref.current, { theme: "outline", size: "large", width: ref.current.offsetWidth || 320, text: context === "signup" ? "signup_with" : "signin_with" });
    }).catch(() => setFailed(true));
    return () => { cancelled = true; };
  }, [clientId, context]);

  if (!clientId) return null;
  return (
    <div className="space-y-3" data-testid="google-sign-in">
      <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>
      <div ref={ref} className="flex min-h-10 justify-center" />
      {failed ? <p className="text-center text-xs text-muted-foreground">Google sign-in could not load. Use your mobile number or email instead.</p> : null}
    </div>
  );
}
