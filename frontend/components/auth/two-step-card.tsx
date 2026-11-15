"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, ShieldCheck } from "lucide-react";
import { authService } from "@/services/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

/** Two-step sign-in with an authenticator app (Google Authenticator, Microsoft Authenticator, Authy…). */
export function TwoStepCard({ onChange }: { onChange: () => Promise<void> }) {
  const required = useSearchParams().get("mfa") === "required";  // sent here because a clinic requires it
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["mfa-status"], queryFn: authService.mfaStatus });
  const [setup, setSetup] = useState<{ secret: string; qr_data_url: string } | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [turningOff, setTurningOff] = useState(false);

  const done = async () => { setCode(""); setPassword(""); await queryClient.invalidateQueries({ queryKey: ["mfa-status"] }); await onChange(); };
  const start = useMutation({ mutationFn: authService.mfaSetup, onSuccess: (s) => { setSetup(s); setCodes(null); }, onError: (e) => toast.error(errorMessage(e)) });
  const enable = useMutation({
    mutationFn: () => authService.mfaEnable(code.trim()),
    onSuccess: async (r) => { setCodes(r.recovery_codes); setSetup(null); toast.success("Two-step sign-in is on"); await done(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const disable = useMutation({
    mutationFn: () => authService.mfaDisable(code.trim(), password || null),
    onSuccess: async () => { setTurningOff(false); toast.success("Two-step sign-in is off"); await done(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const regenerate = useMutation({
    mutationFn: () => authService.mfaRecoveryCodes(code.trim()),
    onSuccess: async (r) => { setCodes(r.recovery_codes); toast.success("New backup codes made. The old ones no longer work."); await done(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const enabled = status.data?.enabled ?? false;
  const copyCodes = async () => {
    try { await navigator.clipboard.writeText(codes!.join("\n")); toast.success("Copied"); } catch { toast.error("Copy failed"); }
  };

  return (
    <Card id="two-step" className="scroll-mt-24" data-testid="two-step-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-5" aria-hidden /> Two-step sign-in
          {enabled ? <Badge variant="success">On</Badge> : <Badge variant="outline">Off</Badge>}
        </CardTitle>
        <CardDescription>After your password or mobile code, also enter a 6-digit code from an authenticator app on your phone. Strongly recommended for clinic owners and administrators.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {required && !enabled ? (
          <Alert variant="destructive" data-testid="mfa-required-notice">
            <AlertDescription>Your clinic requires two-step sign-in for administrators. Turn it on to keep managing the clinic.</AlertDescription>
          </Alert>
        ) : null}

        {codes ? (
          <div className="space-y-3 rounded-xl border border-warning/50 bg-warning/10 p-4" data-testid="recovery-codes">
            <p className="text-sm font-medium">Save these backup codes now. Each works once if you lose your phone. They will not be shown again.</p>
            <ul className="grid grid-cols-2 gap-2 font-mono text-sm sm:grid-cols-5">{codes.map((c) => <li key={c} className="rounded bg-background px-2 py-1 text-center">{c}</li>)}</ul>
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={copyCodes}><Copy /> Copy</Button>
              <Button type="button" size="sm" onClick={() => setCodes(null)}>I have saved them</Button>
            </div>
          </div>
        ) : null}

        {!enabled && !setup ? (
          <Button onClick={() => start.mutate()} disabled={start.isPending} data-testid="mfa-start">Set up two-step sign-in</Button>
        ) : null}

        {!enabled && setup ? (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); enable.mutate(); }} data-testid="mfa-setup">
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              <li>Open an authenticator app (Google Authenticator, Microsoft Authenticator, Authy…).</li>
              <li>Scan this code, or type the key below.</li>
              <li>Enter the 6-digit code the app shows.</li>
            </ol>
            <div className="flex flex-wrap items-center gap-4">
              {/* eslint-disable-next-line @next/next/no-img-element -- a data URL made by the server; nothing to optimise */}
              <img src={setup.qr_data_url} alt="QR code for your authenticator app" width={176} height={176} className="rounded-lg border bg-white p-1" />
              <div className="min-w-0 text-sm">
                <p className="text-muted-foreground">Key (if you cannot scan):</p>
                <p className="font-mono break-all" data-testid="mfa-secret">{setup.secret.match(/.{1,4}/g)?.join(" ")}</p>
              </div>
            </div>
            <Field label="Code from the app" htmlFor="mfa_enable_code">
              <Input id="mfa_enable_code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} className="max-w-40 font-mono tracking-[0.3em]" />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" disabled={enable.isPending || code.trim().length !== 6} data-testid="mfa-enable">Turn on</Button>
              <Button type="button" variant="ghost" onClick={() => { setSetup(null); setCode(""); }}>Cancel</Button>
            </div>
          </form>
        ) : null}

        {enabled ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              On since {status.data?.enabled_at ? formatDateTime(status.data.enabled_at) : "—"} · {status.data?.recovery_codes_left ?? 0} backup codes left
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Current code from the app" htmlFor="mfa_manage_code">
                <Input id="mfa_manage_code" inputMode="numeric" autoComplete="one-time-code" maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} className="font-mono" />
              </Field>
              {turningOff ? (
                <Field label="Your password" htmlFor="mfa_password" hint="Leave empty if you sign in with a mobile code or Google.">
                  <Input id="mfa_password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                </Field>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" disabled={regenerate.isPending || code.trim().length < 6} onClick={() => regenerate.mutate()}>New backup codes</Button>
              {turningOff ? (
                <>
                  <Button type="button" variant="destructive" disabled={disable.isPending || code.trim().length < 6} onClick={() => disable.mutate()} data-testid="mfa-disable">Turn off</Button>
                  <Button type="button" variant="ghost" onClick={() => setTurningOff(false)}>Keep it on</Button>
                </>
              ) : (
                <Button type="button" variant="ghost" disabled={required} onClick={() => setTurningOff(true)}>Turn off…</Button>
              )}
            </div>
            {required ? <p className="text-xs text-muted-foreground">Your clinic requires it, so it cannot be turned off.</p> : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
