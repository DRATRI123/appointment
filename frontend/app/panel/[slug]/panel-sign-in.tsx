"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LockKeyhole, MonitorSmartphone } from "lucide-react";
import { ME_QUERY_KEY, defaultDestination } from "@/components/auth/auth-provider";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/forms/field";
import { ApiError } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";
import { clearPanelSession, isFramed, panelSession, parentOrigin, rememberPanelSlug, savePanelSession, type PanelTokens } from "@/lib/panel-session";
import { safeNextPath } from "@/lib/safe-redirect";
import { panelService } from "@/services/panel";
import { usersService } from "@/services/users";
import type { MeResponse } from "@/types/auth";

const noop = () => () => {};
const PANEL_AREAS = /^\/(admin|professional)(\/|$)/;

/** Only admin screens may be opened from here (anything else: the person's usual start page). */
function destination(next: string | null, me: MeResponse): string {
  const safe = safeNextPath(next);
  return safe && PANEL_AREAS.test(safe) ? safe : defaultDestination(me);
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">{children}</main>;
}

/**
 * /panel/<clinic>: the page the clinic's own app shows in its iframe. It asks for a sign-in (only people with the
 * "panel:use" permission get in), then opens the admin screens inside the same frame.
 */
export function PanelSignIn() {
  const { slug } = useParams<{ slug: string }>();
  const next = useSearchParams().get("next");
  const router = useRouter();
  const queryClient = useQueryClient();
  const framed = useSyncExternalStore(noop, isFramed, () => null);
  const [mfaToken, setMfaToken] = useState<string | null>(null);

  useEffect(() => {
    if (framed) rememberPanelSlug(slug);
  }, [framed, slug]);

  const policy = useQuery({ queryKey: ["panel-policy", slug], queryFn: () => panelService.policy(slug), enabled: framed === true, retry: false });
  const open = policy.data?.enabled === true;
  // Already signed in inside this frame (a reload, or coming back after the screen locked): go straight in.
  const resume = useQuery({
    queryKey: ["panel-resume", slug],
    queryFn: async () => {
      if (panelSession()?.slug !== slug) return null;
      try {
        return await usersService.me();
      } catch {
        clearPanelSession();
        return null;
      }
    },
    enabled: open,
    retry: false,
    gcTime: 0,
  });

  useEffect(() => {
    if (resume.data) {
      queryClient.setQueryData(ME_QUERY_KEY, resume.data);
      router.replace(destination(next, resume.data));
    }
  }, [resume.data, next, router, queryClient]);

  async function finish(tokens: PanelTokens) {
    savePanelSession(slug, tokens);
    const me = await usersService.me();
    queryClient.setQueryData(ME_QUERY_KEY, me);
    router.replace(destination(next, me));
  }

  if (framed === false) {
    return (
      <Shell>
        <Card className="w-full max-w-md" data-testid="panel-not-framed">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl"><MonitorSmartphone className="size-5 text-primary" aria-hidden /> Opens inside your clinic app</CardTitle>
            <CardDescription>This page is shown inside your clinic&apos;s own app. To use the appointment app on its own, sign in normally.</CardDescription>
          </CardHeader>
          <CardContent><Button asChild className="w-full"><Link href="/login">Go to sign in</Link></Button></CardContent>
        </Card>
      </Shell>
    );
  }
  if (framed === null || policy.isLoading || (open && (resume.isLoading || resume.data))) {
    return <Shell><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading" /></Shell>;
  }
  if (!open) {
    return (
      <Shell>
        <Card className="w-full max-w-md" data-testid="panel-off">
          <CardHeader>
            <CardTitle className="text-xl">Admin panel is not switched on</CardTitle>
            <CardDescription>
              The clinic administrator can switch it on in the appointment app: Admin → Panel in your app, and add this app&apos;s web address there.
            </CardDescription>
          </CardHeader>
        </Card>
      </Shell>
    );
  }

  return (
    <Shell>
      <Card className="w-full max-w-md" data-testid="panel-sign-in">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl"><LockKeyhole className="size-5 text-primary" aria-hidden /> {policy.data?.organization_name}</CardTitle>
          <CardDescription>
            {mfaToken ? "Open your authenticator app and enter the 6-digit code." : "Sign in to open the appointment admin panel. Only people the clinic allows can sign in here."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mfaToken ? (
            <MfaForm slug={slug} token={mfaToken} onDone={finish} onRestart={() => setMfaToken(null)} />
          ) : (
            <PasswordForm slug={slug} onDone={finish} onMfa={setMfaToken} />
          )}
        </CardContent>
      </Card>
    </Shell>
  );
}

function PasswordForm({ slug, onDone, onMfa }: { slug: string; onDone: (t: PanelTokens) => Promise<void>; onMfa: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onDone(await panelService.login(slug, { email: email.trim(), password, parent_origin: parentOrigin() }));
    } catch (err) {
      if (err instanceof ApiError && err.code === "mfa_required" && err.body?.mfa_token) onMfa(err.body.mfa_token);
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" data-testid="panel-login-form">
      <Field label="Email" htmlFor="panel_email">
        <Input id="panel_email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Password" htmlFor="panel_password">
        <Input id="panel_password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      {error ? <Alert variant="destructive" data-testid="panel-error"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <Button type="submit" className="w-full" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : null} Sign in</Button>
    </form>
  );
}

function MfaForm({ slug, token, onDone, onRestart }: { slug: string; token: string; onDone: (t: PanelTokens) => Promise<void>; onRestart: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onDone(await panelService.mfa(slug, token, code.trim()));
    } catch (err) {
      if (err instanceof ApiError && (err.code === "mfa_token_expired" || err.code === "mfa_token_invalid")) onRestart();
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Authenticator code" htmlFor="panel_code">
        <Input id="panel_code" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)}
          className="text-center font-mono text-lg tracking-[0.4em]" />
      </Field>
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <Button type="submit" className="w-full" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : null} Continue</Button>
      <Button type="button" variant="ghost" className="w-full" onClick={onRestart}>Back</Button>
    </form>
  );
}
