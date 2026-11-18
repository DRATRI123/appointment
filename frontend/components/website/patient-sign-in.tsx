"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Smartphone } from "lucide-react";
import { ME_QUERY_KEY } from "@/components/auth/auth-provider";
import { ApiError } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";
import { authService } from "@/services/auth";

/**
 * Patients sign in right on the clinic's website: mobile number or email → one-time code → done. No password, no
 * account to create (the first code creates it), no staff options. Every booking made with that number or email then
 * shows up (server: app/services/customer_link.py).
 */
export function PatientSignIn({ next }: { next: string }) {
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<"start" | "contact" | "code">("start");
  const [contact, setContact] = useState("");
  const [sentTo, setSentTo] = useState({ identifier: "", channel: "" });
  const [code, setCode] = useState("");
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [staffAccount, setStaffAccount] = useState(false);

  useEffect(() => {
    if (resendIn <= 0) return;
    const t = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  async function send(event?: React.FormEvent) {
    event?.preventDefault();
    const value = contact.trim();
    if (value.replace(/\D/g, "").length < 10 && !value.includes("@")) {
      setError("Enter your 10-digit mobile number or your email.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await authService.requestOtp(value, "login");
      setSentTo({ identifier: r.identifier, channel: r.channel });
      setDebugCode(r.debug_code ?? null);
      setResendIn(r.resend_in);
      setCode("");
      setStage("code");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function verify(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authService.verifyOtp({ identifier: sentTo.identifier, code: code.trim() });
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ["device-bookings"] });
    } catch (err) {
      // Clinic staff with two-step sign-in use the main sign-in page; patients never get here.
      if (err instanceof ApiError && err.code === "mfa_required") setStaffAccount(true);
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const input = "h-12 w-full rounded-2xl border border-black/10 bg-white px-4 text-base text-gray-900 outline-none focus:border-[var(--primary)] focus:ring-2 focus:ring-[color-mix(in_oklab,var(--primary)_25%,transparent)]";
  const primary = "inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[var(--primary)] px-6 text-sm font-semibold text-[var(--primary-foreground)] disabled:opacity-60";

  return (
    <div className="space-y-4 rounded-3xl bg-white p-5 text-gray-900 shadow-[0_8px_30px_-14px_rgb(0_0_0/0.2)] ring-1 ring-black/5 sm:p-6" data-testid="bookings-sign-in">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_12%,#fff)] text-[var(--primary)]"><Smartphone className="size-6" aria-hidden /></span>
        <div className="flex-1">
          <p className="font-semibold">See all your bookings</p>
          <p className="text-sm text-gray-600">
            Booked on another phone, or lost the link? Get a one-time code on the mobile number or email you booked with. No password needed.
          </p>
        </div>
      </div>

      {staffAccount ? (
        <p className="rounded-2xl bg-amber-50 p-4 text-sm text-amber-900" role="alert">
          This is a clinic staff account with two-step sign-in. Please use the{" "}
          <Link href={`/login?next=${encodeURIComponent(next)}`} className="font-semibold underline">staff sign-in page</Link>.
        </p>
      ) : stage === "start" ? (
        <button type="button" className={`${primary} w-full sm:w-auto`} onClick={() => setStage("contact")} data-testid="patient-sign-in-start">Sign in with code</button>
      ) : stage === "contact" ? (
        <form onSubmit={send} className="space-y-3" data-testid="patient-contact-form">
          <label htmlFor="patient_contact" className="block text-sm font-medium">Mobile number or email</label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input id="patient_contact" className={input} inputMode="email" autoComplete="tel" placeholder="98765 43210 or you@email.com" autoFocus
              value={contact} onChange={(e) => { setContact(e.target.value); setError(null); }} aria-invalid={!!error} aria-describedby={error ? "patient-error" : undefined} />
            <button type="submit" className={`${primary} shrink-0`} disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : null} Send code</button>
          </div>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-3" data-testid="patient-code-form">
          <p className="text-sm text-gray-600">
            Code sent by {sentTo.channel === "email" ? "email" : "SMS"} to <span className="font-medium text-gray-900">{sentTo.identifier}</span>.{" "}
            <button type="button" className="font-medium text-[var(--primary)] underline-offset-4 hover:underline" onClick={() => { setStage("contact"); setError(null); }}>Change</button>
          </p>
          {debugCode ? <p className="rounded-2xl bg-sky-50 p-3 text-sm text-sky-900" data-testid="patient-debug-code">Development mode: your code is <strong className="font-mono">{debugCode}</strong></p> : null}
          <label htmlFor="patient_code" className="block text-sm font-medium">One-time code</label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input id="patient_code" className={`${input} text-center font-mono text-lg tracking-[0.4em]`} inputMode="numeric" autoComplete="one-time-code" placeholder="••••••" autoFocus
              value={code} onChange={(e) => { setCode(e.target.value.replace(/\D/g, "").slice(0, 8)); setError(null); }} aria-invalid={!!error} aria-describedby={error ? "patient-error" : undefined} />
            <button type="submit" className={`${primary} shrink-0`} disabled={busy || code.length < 4}>{busy ? <Loader2 className="size-4 animate-spin" /> : null} Verify</button>
          </div>
          <button type="button" className="text-sm font-medium text-gray-600 disabled:opacity-50" disabled={resendIn > 0 || busy} onClick={() => void send()}>
            {resendIn > 0 ? `Send again in ${resendIn}s` : "Send the code again"}
          </button>
        </form>
      )}
      {error ? <p id="patient-error" className="text-sm text-rose-700" role="alert" data-testid="patient-error">{error}</p> : null}
    </div>
  );
}
