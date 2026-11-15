"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { BadgeCheck, Loader2, Mail, MessageSquareText, Pencil, RefreshCw, ShieldCheck } from "lucide-react";
import { publicBooking, type VerificationChallenge, type VerificationChannel, type VerificationOptions } from "@/services/booking";
import { SocialIcon } from "@/components/website/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

export interface Verified { channel: VerificationChannel; destination: string; token: string }

const METHODS: Record<VerificationChannel, { label: string; via: string; icon: React.ReactNode }> = {
  sms: { label: "Text message (SMS)", via: "SMS", icon: <MessageSquareText className="size-5" aria-hidden /> },
  whatsapp: { label: "WhatsApp", via: "WhatsApp", icon: <SocialIcon network="whatsapp" className="size-5" /> },
  email: { label: "Email", via: "email", icon: <Mail className="size-5" aria-hidden /> },
};

/** Normalise like the server: Indian 10-digit numbers get +91. */
export function e164(raw: string): string {
  const v = raw.replace(/[\s()-]/g, "");
  if (/^[6-9]\d{9}$/.test(v)) return `+91${v}`;
  if (/^0[6-9]\d{9}$/.test(v)) return `+91${v.slice(1)}`;
  return v.startsWith("+") ? v : `+${v}`;
}

/** Is the verification still about the details on the form? (Editing the number or email after verifying undoes it.) */
export function stillVerified(v: Verified | null, mobile: string, email: string): boolean {
  if (!v) return false;
  return v.channel === "email" ? v.destination === email.trim().toLowerCase() : !!mobile && v.destination === e164(mobile);
}

export function ContactVerification({ slug, holdId, sessionKey, options, mobile, mobileValid, email, emailValid, verified, onVerified, onNeedContact }: {
  slug: string; holdId: string; sessionKey: string; options: VerificationOptions;
  mobile: string; mobileValid: boolean; email: string; emailValid: boolean;
  verified: Verified | null; onVerified: (v: Verified) => void; onNeedContact: (field: "mobile" | "email") => void;
}) {
  const [channel, setChannel] = useState<VerificationChannel>(options.default_channel ?? options.channels[0]);
  const [challenge, setChallenge] = useState<(VerificationChallenge & { sentAt: number; to: string }) | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<{ text: string; kind: "code" | "send" } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const codeInput = useRef<HTMLInputElement>(null);
  const isEmail = channel === "email";
  const target = isEmail ? email.trim().toLowerCase() : mobile;
  const targetValid = isEmail ? emailValid && !!email.trim() : mobileValid;
  const length = challenge?.code_length ?? options.code_length;

  useEffect(() => {
    if (!challenge) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [challenge]);

  const accept = (c: VerificationChallenge) => {
    setChallenge({ ...c, sentAt: Date.now(), to: target });
    setNow(Date.now());
    setCode("");
    setError(null);
    setTimeout(() => codeInput.current?.focus(), 50);
  };
  const fail = (e: unknown, kind: "code" | "send") => {
    const c = e instanceof ApiError ? e.code : "";
    if (c === "otp_expired" || c === "otp_superseded" || c === "otp_not_found") setError({ text: `${errorMessage(e)}`, kind });
    else if (c === "otp_delivery_failed") setError({ text: `${errorMessage(e)}${options.channels.length > 1 ? " You can also choose another method above." : ""}`, kind: "send" });
    else setError({ text: errorMessage(e), kind });
  };

  const send = useMutation({ mutationFn: () => publicBooking.startVerification(slug, { channel, destination: target, hold_id: holdId, session_key: sessionKey }), onSuccess: accept, onError: (e) => fail(e, "send") });
  const resend = useMutation({ mutationFn: () => publicBooking.resendVerification(slug, challenge!.challenge_id, sessionKey), onSuccess: accept, onError: (e) => fail(e, "send") });
  const check = useMutation({
    mutationFn: (value: string) => publicBooking.verifyCode(slug, challenge!.challenge_id, { code: value, session_key: sessionKey }),
    onSuccess: (r) => { setError(null); onVerified({ channel: r.channel, destination: r.destination, token: r.verification_token }); },
    onError: (e) => { fail(e, "code"); setCode(""); codeInput.current?.focus(); },
  });

  if (verified) {
    return (
      <div className="pb-enter flex items-center gap-3 rounded-2xl border border-success/40 bg-success/10 p-4 text-sm" role="status" data-testid="contact-verified">
        <BadgeCheck className="size-5 shrink-0 text-success-ink" aria-hidden />
        <span><span className="font-medium">Verified by {METHODS[verified.channel].via}.</span> <span className="text-muted-foreground">You can review and confirm your booking.</span></span>
      </div>
    );
  }

  const sentElsewhere = challenge && (challenge.channel !== channel || challenge.to !== target);
  const waiting = challenge ? Math.max(0, Math.ceil((challenge.sentAt + challenge.resend_after_seconds * 1000 - now) / 1000)) : 0;
  const expired = challenge ? now > challenge.sentAt + challenge.expires_in_seconds * 1000 : false;

  return (
    <div className="space-y-4 rounded-2xl border bg-background p-4 sm:p-5" data-testid="otp-panel">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><ShieldCheck className="size-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="font-semibold">Verify your contact details</p>
          <p className="text-sm text-muted-foreground">We send a one-time code so the clinic can be sure it can reach you. No account is created.</p>
        </div>
      </div>

      {!challenge || sentElsewhere ? (
        <>
          {options.channels.length > 1 ? (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Send the code by</legend>
              <div className="grid gap-2 sm:grid-cols-3" role="radiogroup">
                {options.channels.map((c) => (
                  <label key={c} className={cn("flex cursor-pointer items-center gap-2.5 rounded-xl border p-3 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary", channel === c ? "border-primary bg-primary/5 ring-2 ring-primary/15" : "hover:bg-muted")} data-testid={`channel-${c}`}>
                    <input type="radio" name="otp-channel" className="sr-only" checked={channel === c} onChange={() => { setChannel(c); setError(null); }} />
                    <span className={cn("text-muted-foreground", channel === c && "text-primary")}>{METHODS[c].icon}</span>
                    <span className="font-medium">{METHODS[c].label}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}
          <Button type="button" variant="outline" className="h-11 w-full" disabled={send.isPending} data-testid="send-code"
            onClick={() => { if (!targetValid) { onNeedContact(isEmail ? "email" : "mobile"); return; } send.mutate(); }}>
            {send.isPending ? <Loader2 className="animate-spin" /> : METHODS[channel].icon}
            {targetValid ? <>Send code to {isEmail ? email.trim() : mobile}</> : isEmail ? "Enter your email above first" : "Enter your mobile number above first"}
          </Button>
        </>
      ) : (
        <div className="space-y-3">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span>Enter the {length}-digit code sent by {METHODS[challenge.channel].via} to <span className="font-medium tabular-nums">{challenge.destination}</span></span>
            <button type="button" className="inline-flex items-center gap-1 text-xs text-primary hover:underline" onClick={() => { setChallenge(null); setCode(""); setError(null); document.getElementById(isEmail ? "bk_email" : "bk_mobile")?.focus(); }}>
              <Pencil className="size-3" aria-hidden />{isEmail ? "Change email" : "Change number"}
            </button>
            {options.channels.length > 1 ? <button type="button" className="text-xs text-primary hover:underline" onClick={() => { setChallenge(null); setError(null); }}>Use another method</button> : null}
          </p>
          <div className="flex gap-2">
            <Label htmlFor="bk_code" className="sr-only">One-time code</Label>
            <Input id="bk_code" ref={codeInput} inputMode="numeric" autoComplete="one-time-code" pattern={`\\d{${length}}`} maxLength={length} value={code} data-testid="otp-input"
              aria-invalid={!!error} aria-describedby={error ? "bk_code-error" : "bk_code-help"}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, length);
                setCode(v);
                if (v.length === length && !check.isPending) check.mutate(v);
              }}
              className="h-12 flex-1 text-center font-mono text-xl tracking-[0.5em]" placeholder={"•".repeat(length)} />
            <Button type="button" className="h-12" disabled={code.length !== length || check.isPending} onClick={() => check.mutate(code)} data-testid="verify-code">
              {check.isPending ? <Loader2 className="animate-spin" /> : null} Verify
            </Button>
          </div>
          <p id="bk_code-help" className="text-xs text-muted-foreground" aria-live="polite">
            {expired ? <span className="text-destructive-ink">This code has expired. </span> : null}
            Didn&apos;t get it?{" "}
            {challenge.resends_left <= 0 ? <span>No more resends for this request{options.channels.length > 1 ? "; try another method" : ""}.</span>
              : waiting > 0 ? <span data-testid="resend-countdown">Resend in {waiting}s</span>
                : <button type="button" className="inline-flex items-center gap-1 font-medium text-primary hover:underline" onClick={() => resend.mutate()} disabled={resend.isPending} data-testid="resend-code"><RefreshCw className="size-3" aria-hidden />Resend code</button>}
          </p>
        </div>
      )}
      {error ? <p id="bk_code-error" className="text-sm text-destructive-ink" role="alert" data-testid="otp-error">{error.text}</p> : null}
    </div>
  );
}
