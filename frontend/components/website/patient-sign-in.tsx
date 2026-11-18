"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LockKeyhole, Mail, MessageSquareText, Pencil, RefreshCw, ShieldCheck } from "lucide-react";
import { ME_QUERY_KEY } from "@/components/auth/auth-provider";
import { e164 } from "@/components/public-booking/contact-verification";
import { ApiError } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { bookingSessionKey } from "@/services/booking";
import { patientSignIn, type SignInChallenge, type SignInChannel } from "@/services/patient";
import { SocialIcon } from "./icons";

const METHODS: Record<SignInChannel, { label: string; via: string; icon: React.ReactNode }> = {
  sms: { label: "SMS", via: "SMS", icon: <MessageSquareText className="size-4" aria-hidden /> },
  whatsapp: { label: "WhatsApp", via: "WhatsApp", icon: <SocialIcon network="whatsapp" className="size-4" /> },
  email: { label: "Email", via: "email", icon: <Mail className="size-4" aria-hidden /> },
};

/**
 * Patients sign in on the clinic's website: mobile number (SMS / WhatsApp) or email → one-time code → signed in. No
 * password and no account to create. The code is sent through the clinic's own channels; the website never sees it.
 * Then every booking made with that number or email shows up (server: app/services/customer_link.py).
 */
export function PatientSignIn({ slug, next }: { slug: string; next: string }) {
  const queryClient = useQueryClient();
  const options = useQuery({ queryKey: ["patient-sign-in", slug], queryFn: () => patientSignIn.options(slug), staleTime: 5 * 60_000 });
  const [picked, setPicked] = useState<SignInChannel | null>(null);
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [challenge, setChallenge] = useState<(SignInChallenge & { sentAt: number }) | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"send" | "verify" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [staffAccount, setStaffAccount] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const codeInput = useRef<HTMLInputElement>(null);

  const channels = options.data?.channels ?? [];
  const channel: SignInChannel | null = picked && channels.includes(picked) ? picked : options.data?.default_channel ?? channels[0] ?? null;
  const isEmail = channel === "email";
  const length = challenge?.code_length ?? options.data?.code_length ?? 6;

  useEffect(() => {
    if (!challenge) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [challenge]);

  function accept(c: SignInChallenge) {
    setChallenge({ ...c, sentAt: Date.now() });
    setNow(Date.now());
    setCode("");
    setError(null);
    setTimeout(() => codeInput.current?.focus(), 50);
  }

  async function send(event?: React.FormEvent) {
    event?.preventDefault();
    if (!channel) return;
    const destination = isEmail ? email.trim().toLowerCase() : e164(mobile);
    if (isEmail ? !/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(destination) : !/^\+\d{10,15}$/.test(destination)) {
      setError(isEmail ? "Enter the email address you booked with." : "Enter your 10-digit mobile number.");
      return;
    }
    setBusy("send");
    setError(null);
    try {
      accept(await patientSignIn.start(slug, { channel, destination, session_key: bookingSessionKey() }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function resend() {
    if (!challenge) return;
    setBusy("send");
    setError(null);
    try {
      accept(await patientSignIn.resend(slug, challenge.challenge_id, bookingSessionKey()));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function verify(value: string) {
    if (!challenge || busy) return;
    setBusy("verify");
    setError(null);
    try {
      await patientSignIn.verify(slug, challenge.challenge_id, { code: value, session_key: bookingSessionKey() });
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ["device-bookings"] });
    } catch (err) {
      if (err instanceof ApiError && err.code === "mfa_required") setStaffAccount(true);
      else {
        setError(errorMessage(err));
        setCode("");
        codeInput.current?.focus();
      }
    } finally {
      setBusy(null);
    }
  }

  const waiting = challenge ? Math.max(0, Math.ceil((challenge.sentAt + challenge.resend_after_seconds * 1000 - now) / 1000)) : 0;
  const expired = challenge ? now > challenge.sentAt + challenge.expires_in_seconds * 1000 : false;
  const field = "h-12 w-full rounded-2xl border border-black/10 bg-white px-4 text-base text-gray-900 outline-none transition focus:border-[var(--primary)] focus:ring-4 focus:ring-[color-mix(in_oklab,var(--primary)_18%,transparent)]";
  const primary = "inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[var(--primary)] px-6 text-sm font-semibold text-[var(--primary-foreground)] shadow-sm transition hover:brightness-105 disabled:opacity-60";

  return (
    <section aria-labelledby="patient-sign-in-title" className="overflow-hidden rounded-3xl bg-white text-gray-900 shadow-[0_12px_40px_-18px_rgb(0_0_0/0.25)] ring-1 ring-black/5" data-testid="bookings-sign-in">
      <div className="flex items-start gap-4 border-b border-black/5 bg-[color-mix(in_oklab,var(--primary)_6%,#fff)] p-5 sm:p-6">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm"><LockKeyhole className="size-5" aria-hidden /></span>
        <div>
          <h2 id="patient-sign-in-title" className="text-lg font-semibold">Sign in to see all your bookings</h2>
          <p className="mt-0.5 text-sm text-gray-600">Booked on another phone or lost the link? We send a one-time code to the mobile number or email you booked with. No password.</p>
        </div>
      </div>

      <div className="space-y-4 p-5 sm:p-6">
        {staffAccount ? (
          <p className="rounded-2xl bg-amber-50 p-4 text-sm text-amber-900" role="alert">
            This is a clinic staff account with two-step sign-in. Please use the{" "}
            <Link href={`/login?next=${encodeURIComponent(next)}`} className="font-semibold underline">staff sign-in page</Link>.
          </p>
        ) : options.isLoading ? (
          <div className="h-28 animate-pulse rounded-2xl bg-gray-100" />
        ) : !channel ? (
          <p className="rounded-2xl bg-gray-50 p-4 text-sm text-gray-700" role="status">Online sign-in is not available at this clinic right now. Please contact the clinic for your booking details.</p>
        ) : !challenge ? (
          <form onSubmit={send} className="space-y-4" data-testid="patient-contact-form" noValidate>
            {channels.length > 1 ? (
              <fieldset>
                <legend className="mb-2 text-sm font-medium">Get the code by</legend>
                <div className="flex flex-wrap gap-2" role="radiogroup">
                  {channels.map((c) => (
                    <label key={c} data-testid={`signin-channel-${c}`}
                      className={cn("inline-flex cursor-pointer items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--primary)]",
                        channel === c ? "border-[var(--primary)] bg-[color-mix(in_oklab,var(--primary)_10%,#fff)] text-[var(--primary)]" : "border-black/10 text-gray-700 hover:border-black/20")}>
                      <input type="radio" name="signin-channel" className="sr-only" checked={channel === c} onChange={() => { setPicked(c); setError(null); }} />
                      {METHODS[c].icon}{METHODS[c].label}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}
            {isEmail ? (
              <div className="space-y-1.5">
                <label htmlFor="patient_email" className="block text-sm font-medium">Email address</label>
                <input id="patient_email" type="email" className={field} autoComplete="email" placeholder="you@example.com" value={email}
                  onChange={(e) => { setEmail(e.target.value); setError(null); }} aria-invalid={!!error} aria-describedby={error ? "patient-error" : undefined} />
              </div>
            ) : (
              <div className="space-y-1.5">
                <label htmlFor="patient_mobile" className="block text-sm font-medium">Mobile number</label>
                <div className="flex">
                  <span className="inline-flex h-12 items-center rounded-l-2xl border border-r-0 border-black/10 bg-gray-50 px-3 text-base text-gray-600">+91</span>
                  <input id="patient_mobile" type="tel" inputMode="numeric" className={cn(field, "rounded-l-none")} autoComplete="tel-national" placeholder="98765 43210" value={mobile}
                    onChange={(e) => { setMobile(e.target.value.replace(/[^\d\s+]/g, "").slice(0, 16)); setError(null); }} aria-invalid={!!error} aria-describedby={error ? "patient-error" : undefined} />
                </div>
              </div>
            )}
            <button type="submit" className={cn(primary, "w-full")} disabled={busy === "send"} data-testid="patient-send-code">
              {busy === "send" ? <Loader2 className="size-4 animate-spin" /> : METHODS[channel].icon} Send code by {METHODS[channel].via}
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void verify(code); }} className="space-y-4" data-testid="patient-code-form">
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-700">
              <span>Enter the {length}-digit code sent by {METHODS[challenge.channel].via} to <span className="font-semibold tabular-nums text-gray-900">{challenge.destination}</span></span>
              <button type="button" className="inline-flex items-center gap-1 font-medium text-[var(--primary)] hover:underline" onClick={() => { setChallenge(null); setError(null); }}>
                <Pencil className="size-3" aria-hidden /> Change
              </button>
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <label htmlFor="patient_code" className="sr-only">One-time code</label>
              <input id="patient_code" ref={codeInput} className={cn(field, "text-center font-mono text-xl tracking-[0.5em]")} inputMode="numeric" autoComplete="one-time-code"
                pattern={`\\d{${length}}`} maxLength={length} placeholder={"•".repeat(length)} value={code} data-testid="patient-code"
                aria-invalid={!!error} aria-describedby={error ? "patient-error" : "patient-code-help"}
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, "").slice(0, length);
                  setCode(v);
                  setError(null);
                  if (v.length === length) void verify(v);
                }} />
              <button type="submit" className={cn(primary, "shrink-0")} disabled={code.length !== length || busy === "verify"} data-testid="patient-verify">
                {busy === "verify" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" aria-hidden />} Verify
              </button>
            </div>
            <p id="patient-code-help" className="text-sm text-gray-600" aria-live="polite">
              {expired ? <span className="text-rose-700">This code has expired. </span> : null}
              Didn&apos;t get it?{" "}
              {challenge.resends_left <= 0 ? <span>No more codes for this request{channels.length > 1 ? "; choose another method" : ""}.</span>
                : waiting > 0 ? <span data-testid="patient-resend-countdown">Send again in {waiting}s</span>
                  : <button type="button" className="inline-flex items-center gap-1 font-medium text-[var(--primary)] hover:underline" onClick={() => void resend()} disabled={busy !== null}><RefreshCw className="size-3" aria-hidden />Send a new code</button>}
            </p>
          </form>
        )}
        {error ? <p id="patient-error" className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert" data-testid="patient-error">{error}</p> : null}
        <p className="flex items-center gap-1.5 text-xs text-gray-500"><ShieldCheck className="size-3.5" aria-hidden /> Your number is used only to find your bookings at this clinic.</p>
      </div>
    </section>
  );
}
