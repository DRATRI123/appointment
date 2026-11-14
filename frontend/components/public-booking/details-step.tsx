"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { BadgeCheck, Loader2, MessageSquareText, Pencil, ShieldCheck } from "lucide-react";
import { publicBooking } from "@/services/booking";
import { publicForms } from "@/services/customers";
import { DynamicForm, type Answers } from "@/components/forms/dynamic-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { PublicForm } from "@/types/customer";

export interface Details {
  full_name: string;
  mobile: string;
  email: string;
  notes: string;
  whatsapp: boolean;
  dependentId: string;
}

const MOBILE = /^(\+[1-9]\d{7,14}|[6-9]\d{9}|0[6-9]\d{9})$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function digitsOnly(value: string): string {
  return value.replace(/[\s()-]/g, "");
}

export function validateDetails(d: Details): Record<string, string> {
  const errors: Record<string, string> = {};
  if (d.full_name.trim().length < 2) errors.full_name = "Enter the patient's full name.";
  if (!MOBILE.test(digitsOnly(d.mobile))) errors.mobile = "Enter a 10-digit mobile number (or include the country code, e.g. +44…).";
  if (d.email.trim() && !EMAIL.test(d.email.trim())) errors.email = "Enter a valid email address, or leave it empty.";
  return errors;
}

export function DetailsStep({ slug, holdId, sessionKey, details, onChange, verificationRequired, verifiedFor, onVerified, whatsappEnabled, dependents,
  form, answers, onAnswers, formErrors, onContinue }: {
  slug: string; holdId: string; sessionKey: string; details: Details; onChange: (d: Details) => void;
  verificationRequired: boolean; verifiedFor: string | null; onVerified: (mobile: string, token: string) => void;
  whatsappEnabled: boolean; dependents: { id: string; full_name: string; relationship_label: string | null }[];
  form: PublicForm | null | undefined; answers: Answers; onAnswers: (a: Answers) => void; formErrors: Record<string, string>; onContinue: () => void;
}) {
  const [touched, setTouched] = useState(false);
  const errors = validateDetails(details);
  const showError = (key: keyof Details) => (touched ? errors[key] : undefined);
  const mobile = digitsOnly(details.mobile);
  const verified = !verificationRequired || (verifiedFor !== null && verifiedFor === mobile);

  return (
    <form
      className="space-y-6"
      data-testid="details-form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        setTouched(true);
        if (Object.keys(errors).length === 0 && verified) onContinue();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <FieldBlock id="bk_name" label="Patient's full name" error={showError("full_name")} className="sm:col-span-2">
          <Input id="bk_name" autoComplete="name" value={details.full_name} aria-invalid={!!showError("full_name")} aria-describedby={showError("full_name") ? "bk_name-error" : undefined}
            onChange={(e) => onChange({ ...details, full_name: e.target.value })} placeholder="As it should appear on the appointment" className="h-11" />
        </FieldBlock>
        <FieldBlock id="bk_mobile" label="Mobile number" error={showError("mobile")} hint={verificationRequired ? "We'll send a 6-digit code to confirm it." : undefined}>
          <div className="relative">
            <Input id="bk_mobile" type="tel" inputMode="tel" autoComplete="tel" value={details.mobile} aria-invalid={!!showError("mobile")}
              aria-describedby={showError("mobile") ? "bk_mobile-error" : "bk_mobile-hint"} onChange={(e) => onChange({ ...details, mobile: e.target.value })}
              placeholder="98765 43210" className={cn("h-11", verifiedFor && verifiedFor === mobile && "pr-24")} />
            {verificationRequired && verifiedFor && verifiedFor === mobile ? (
              <span className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success-ink" data-testid="mobile-verified"><BadgeCheck className="size-3.5" aria-hidden />Verified</span>
            ) : null}
          </div>
        </FieldBlock>
        <FieldBlock id="bk_email" label="Email (optional)" error={showError("email")} hint="For the confirmation and calendar invite.">
          <Input id="bk_email" type="email" inputMode="email" autoComplete="email" value={details.email} aria-invalid={!!showError("email")}
            aria-describedby={showError("email") ? "bk_email-error" : "bk_email-hint"} onChange={(e) => onChange({ ...details, email: e.target.value })} placeholder="you@example.com" className="h-11" />
        </FieldBlock>
        {dependents.length ? (
          <FieldBlock id="bk_for" label="Who is the appointment for?" className="sm:col-span-2">
            <select id="bk_for" className="h-11 w-full rounded-lg border bg-background px-3 text-sm" value={details.dependentId} onChange={(e) => onChange({ ...details, dependentId: e.target.value })}>
              <option value="">Myself</option>
              {dependents.map((d) => <option key={d.id} value={d.id}>{d.full_name}{d.relationship_label ? ` (${d.relationship_label})` : ""}</option>)}
            </select>
          </FieldBlock>
        ) : null}
        <FieldBlock id="bk_notes" label="Anything the doctor should know? (optional)" className="sm:col-span-2">
          <Textarea id="bk_notes" rows={3} value={details.notes} onChange={(e) => onChange({ ...details, notes: e.target.value })} placeholder="Symptoms, previous treatment, preferred language…" maxLength={2000} />
        </FieldBlock>
        {whatsappEnabled ? (
          <label className="flex items-start gap-2.5 text-sm sm:col-span-2">
            <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={details.whatsapp} onChange={(e) => onChange({ ...details, whatsapp: e.target.checked })} data-testid="whatsapp-opt-in" />
            <span>Send booking updates and reminders to this number on WhatsApp</span>
          </label>
        ) : null}
      </div>

      {form ? (
        <div className="space-y-3 rounded-2xl border bg-muted/30 p-4 sm:p-5" data-testid="booking-form-section">
          <div>
            <p className="font-semibold">{form.name}</p>
            {form.instructions ? <p className="text-sm text-muted-foreground">{form.instructions}</p> : null}
          </div>
          <DynamicForm fields={form.fields} answers={answers} onChange={onAnswers} errors={formErrors} uploadFile={(file) => publicForms.uploadFile(slug, file)} />
        </div>
      ) : null}

      {verificationRequired ? (
        <MobileVerification slug={slug} holdId={holdId} sessionKey={sessionKey} mobile={mobile} mobileValid={!errors.mobile} verified={verifiedFor === mobile && verifiedFor !== null}
          onVerified={(token) => onVerified(mobile, token)} onNeedMobile={() => setTouched(true)} />
      ) : null}

      <Button type="submit" size="lg" className="h-12 w-full text-base" disabled={verificationRequired && !verified} data-testid="details-continue">
        Review booking
      </Button>
      {verificationRequired && !verified ? <p className="-mt-3 text-center text-xs text-muted-foreground">Verify your mobile number to continue.</p> : null}
    </form>
  );
}

function FieldBlock({ id, label, error, hint, className, children }: { id: string; label: string; error?: string; hint?: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? <p id={`${id}-error`} className="text-sm text-destructive-ink" role="alert">{error}</p> : hint ? <p id={`${id}-hint`} className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function MobileVerification({ slug, holdId, sessionKey, mobile, mobileValid, verified, onVerified, onNeedMobile }: {
  slug: string; holdId: string; sessionKey: string; mobile: string; mobileValid: boolean; verified: boolean; onVerified: (token: string) => void; onNeedMobile: () => void;
}) {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const codeInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!sentTo) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [sentTo]);

  const send = useMutation({
    mutationFn: () => publicBooking.sendMobileCode(slug, { mobile, hold_id: holdId, session_key: sessionKey }),
    onSuccess: (r) => {
      setSentTo(mobile);
      setResendAt(Date.now() + r.resend_after_seconds * 1000);
      setNow(Date.now());
      setCode("");
      setError(null);
      setTimeout(() => codeInput.current?.focus(), 50);
    },
    onError: (e) => setError(errorMessage(e)),
  });
  const confirm = useMutation({
    mutationFn: (value: string) => publicBooking.confirmMobileCode(slug, { mobile, code: value, hold_id: holdId, session_key: sessionKey }),
    onSuccess: (r) => { setError(null); onVerified(r.verification_token); },
    onError: (e) => { setError(errorMessage(e)); setCode(""); codeInput.current?.focus(); },
  });

  if (verified) {
    return (
      <div className="pb-enter flex items-center gap-3 rounded-2xl border border-success/40 bg-success/10 p-4 text-sm" role="status">
        <BadgeCheck className="size-5 shrink-0 text-success-ink" aria-hidden />
        <span><span className="font-medium">Mobile number verified.</span> <span className="text-muted-foreground">You can review and confirm your booking.</span></span>
      </div>
    );
  }

  const waiting = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const changed = sentTo !== null && sentTo !== mobile;
  return (
    <div className="space-y-3 rounded-2xl border bg-background p-4 sm:p-5" data-testid="otp-panel">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><ShieldCheck className="size-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="font-semibold">Confirm your mobile number</p>
          <p className="text-sm text-muted-foreground">So the clinic can reach you, we check the number with a one-time code. No account is created.</p>
        </div>
      </div>
      {!sentTo || changed ? (
        <Button type="button" variant="outline" className="h-11 w-full" disabled={send.isPending} data-testid="send-code"
          onClick={() => { if (!mobileValid) { onNeedMobile(); return; } send.mutate(); }}>
          {send.isPending ? <Loader2 className="animate-spin" /> : <MessageSquareText />} Send code to {mobile || "my number"}
        </Button>
      ) : (
        <div className="space-y-3">
          <p className="flex flex-wrap items-center gap-x-2 text-sm">
            <span>Enter the 6-digit code sent to <span className="font-medium tabular-nums">{sentTo}</span></span>
            <button type="button" className="inline-flex items-center gap-1 text-xs text-primary hover:underline" onClick={() => { setSentTo(null); setCode(""); document.getElementById("bk_mobile")?.focus(); }}><Pencil className="size-3" aria-hidden />Change number</button>
          </p>
          <div className="flex gap-2">
            <Label htmlFor="bk_code" className="sr-only">One-time code</Label>
            <Input id="bk_code" ref={codeInput} inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} value={code} data-testid="otp-input"
              aria-invalid={!!error} aria-describedby={error ? "bk_code-error" : undefined}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                setCode(v);
                if (v.length === 6 && !confirm.isPending) confirm.mutate(v);
              }}
              className="h-12 flex-1 text-center font-mono text-xl tracking-[0.5em]" placeholder="••••••" />
            <Button type="button" className="h-12" disabled={code.length !== 6 || confirm.isPending} onClick={() => confirm.mutate(code)} data-testid="verify-code">
              {confirm.isPending ? <Loader2 className="animate-spin" /> : null} Verify
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Didn&apos;t get it?{" "}
            {waiting > 0 ? <span>Resend in {waiting}s</span> : <button type="button" className="font-medium text-primary hover:underline" onClick={() => send.mutate()} disabled={send.isPending}>Resend code</button>}
          </p>
        </div>
      )}
      {error ? <p id="bk_code-error" className="text-sm text-destructive-ink" role="alert" data-testid="otp-error">{error}</p> : null}
    </div>
  );
}
