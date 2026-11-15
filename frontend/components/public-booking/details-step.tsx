"use client";

import { useState } from "react";
import { BadgeCheck } from "lucide-react";
import type { VerificationOptions } from "@/services/booking";
import { publicForms } from "@/services/customers";
import { DynamicForm, type Answers } from "@/components/forms/dynamic-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { ContactVerification, stillVerified, type Verified } from "./contact-verification";
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

export function DetailsStep({ slug, holdId, sessionKey, details, onChange, verificationRequired, verification, verified, onVerified, whatsappEnabled, dependents,
  form, answers, onAnswers, formErrors, onContinue }: {
  slug: string; holdId: string; sessionKey: string; details: Details; onChange: (d: Details) => void;
  verificationRequired: boolean; verification: VerificationOptions | undefined; verified: Verified | null; onVerified: (v: Verified) => void;
  whatsappEnabled: boolean; dependents: { id: string; full_name: string; relationship_label: string | null }[];
  form: PublicForm | null | undefined; answers: Answers; onAnswers: (a: Answers) => void; formErrors: Record<string, string>; onContinue: () => void;
}) {
  const [touched, setTouched] = useState(false);
  const errors = validateDetails(details);
  const showError = (key: keyof Details) => (touched ? errors[key] : undefined);
  const mobile = digitsOnly(details.mobile);
  const isVerified = stillVerified(verified, details.mobile, details.email);
  const ok = !verificationRequired || isVerified;
  const mobileVerified = isVerified && verified?.channel !== "email";
  const emailVerified = isVerified && verified?.channel === "email";

  return (
    <form
      className="space-y-6"
      data-testid="details-form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        setTouched(true);
        if (Object.keys(errors).length === 0 && ok) onContinue();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <FieldBlock id="bk_name" label="Patient's full name" error={showError("full_name")} className="sm:col-span-2">
          <Input id="bk_name" autoComplete="name" value={details.full_name} aria-invalid={!!showError("full_name")} aria-describedby={showError("full_name") ? "bk_name-error" : undefined}
            onChange={(e) => onChange({ ...details, full_name: e.target.value })} placeholder="As it should appear on the appointment" className="h-11" />
        </FieldBlock>
        <FieldBlock id="bk_mobile" label="Mobile number" error={showError("mobile")} hint={verificationRequired && verification?.channels.some((c) => c !== "email") ? "We'll send a one-time code to confirm it." : undefined}>
          <div className="relative">
            <Input id="bk_mobile" type="tel" inputMode="tel" autoComplete="tel" value={details.mobile} aria-invalid={!!showError("mobile")}
              aria-describedby={showError("mobile") ? "bk_mobile-error" : "bk_mobile-hint"} onChange={(e) => onChange({ ...details, mobile: e.target.value })}
              placeholder="98765 43210" className={cn("h-11", mobileVerified && "pr-24")} />
            {verificationRequired && mobileVerified ? (
              <span className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success-ink" data-testid="mobile-verified"><BadgeCheck className="size-3.5" aria-hidden />Verified</span>
            ) : null}
          </div>
        </FieldBlock>
        <FieldBlock id="bk_email" label={verification?.channels.length === 1 && verification.channels[0] === "email" && verificationRequired ? "Email" : "Email (optional)"} error={showError("email")} hint="For the confirmation and calendar invite.">
          <div className="relative">
            <Input id="bk_email" type="email" inputMode="email" autoComplete="email" value={details.email} aria-invalid={!!showError("email")}
              aria-describedby={showError("email") ? "bk_email-error" : "bk_email-hint"} onChange={(e) => onChange({ ...details, email: e.target.value })} placeholder="you@example.com" className={cn("h-11", emailVerified && "pr-24")} />
            {verificationRequired && emailVerified ? (
              <span className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success-ink" data-testid="email-verified"><BadgeCheck className="size-3.5" aria-hidden />Verified</span>
            ) : null}
          </div>
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

      {verificationRequired && verification ? (
        verification.channels.length ? (
          <ContactVerification slug={slug} holdId={holdId} sessionKey={sessionKey} options={verification} mobile={mobile} mobileValid={!errors.mobile}
            email={details.email} emailValid={!errors.email} verified={isVerified ? verified : null} onVerified={onVerified}
            onNeedContact={(field) => { setTouched(true); document.getElementById(field === "email" ? "bk_email" : "bk_mobile")?.focus(); }} />
        ) : (
          <p className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm" role="alert">Online verification is not available right now, so online booking can&apos;t be completed. Please call the clinic to book.</p>
        )
      ) : null}

      <Button type="submit" size="lg" className="h-12 w-full text-base" disabled={!ok} data-testid="details-continue">
        Review booking
      </Button>
      {!ok ? <p className="-mt-3 text-center text-xs text-muted-foreground">Verify your contact details to continue.</p> : null}
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
