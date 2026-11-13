"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Check, Clock, Loader2, MapPin, UserRound } from "lucide-react";
import { useOrg } from "../org-provider";
import { useAuth } from "@/components/auth/auth-provider";
import { publicCatalog } from "@/services/catalog";
import { bookingSessionKey, publicBooking } from "@/services/booking";
import { customerSelfService, publicForms } from "@/services/customers";
import { DynamicForm, formErrorsFromApi, type Answers } from "@/components/forms/dynamic-form";
import { SlotPicker } from "@/components/booking/slot-picker";
import { HoldCountdown } from "@/components/booking/hold-countdown";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateLong, formatTime } from "@/lib/format";
import { cn, formatPaise } from "@/lib/utils";
import type { Hold, Slot } from "@/types/booking";

const STEPS = ["Service", "Location", "Professional", "Date & time", "Your details"] as const;

export function BookingWizard() {
  const { slug, data } = useOrg();
  const params = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const sessionKey = useMemo(() => (typeof window === "undefined" ? "" : bookingSessionKey()), []);

  const [serviceId, setServiceId] = useState<string | null>(params.get("service"));
  const [branchId, setBranchId] = useState<string | null>(data.branches.length === 1 ? data.branches[0].id : null);
  const [professionalId, setProfessionalId] = useState<string | null | "any">(params.get("professional") ?? null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [hold, setHold] = useState<Hold | null>(null);
  const [tz, setTz] = useState<string>(data.organization.timezone);
  const [draft, setDraft] = useState<{ full_name?: string; mobile?: string; email?: string; notes: string }>({ notes: "" });
  const [answers, setAnswers] = useState<Answers>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [dependentId, setDependentId] = useState("");
  const [whatsappOptIn, setWhatsappOptIn] = useState(false);
  const [couponInput, setCouponInput] = useState("");
  const [coupon, setCoupon] = useState<string | null>(null);
  // Signed-in users get their profile pre-filled; anything they type wins.
  const details = { full_name: draft.full_name ?? user?.full_name ?? "", mobile: draft.mobile ?? user?.mobile ?? "", email: draft.email ?? user?.email ?? "", notes: draft.notes };
  const setDetails = (next: typeof details) => setDraft({ full_name: next.full_name, mobile: next.mobile, email: next.email, notes: next.notes });

  const services = useQuery({ queryKey: ["public-services", slug, branchId], queryFn: () => publicCatalog.services(slug, { branch_id: branchId ?? undefined }) });
  const professionals = useQuery({
    queryKey: ["public-pros", slug, branchId, serviceId],
    queryFn: () => publicCatalog.professionals(slug, { branch_id: branchId ?? undefined, service_id: serviceId ?? undefined }),
    enabled: !!serviceId && !!branchId,
  });
  const quote = useQuery({
    queryKey: ["quote", slug, serviceId, branchId, slot?.professional_id, coupon],
    queryFn: () => publicBooking.quote(slug, { service_id: serviceId!, branch_id: branchId!, professional_id: slot?.professional_id, coupon_code: coupon ?? undefined }),
    enabled: !!serviceId && !!branchId,
    retry: false,
  });

  const bookingForm = useQuery({ queryKey: ["public-form", slug, serviceId, branchId], queryFn: () => publicForms.form(slug, { service_id: serviceId!, branch_id: branchId! }), enabled: !!serviceId && !!branchId });
  const dependents = useQuery({ queryKey: ["my-dependents-for", data.organization.id], queryFn: () => customerSelfService.dependents(data.organization.id), enabled: !!user, retry: false });
  const service = services.data?.find((s) => s.id === serviceId) ?? null;
  const step = !serviceId ? 0 : !branchId ? 1 : professionalId === null ? 2 : !hold ? 3 : 4;

  const releaseHold = useCallback(async () => {
    if (hold) {
      try { await publicBooking.releaseHold(slug, hold.id, sessionKey); } catch { /* ignore */ }
    }
    setHold(null);
    setSlot(null);
  }, [hold, slug, sessionKey]);

  const reserve = useMutation({
    mutationFn: (s: Slot) => publicBooking.hold(slug, { professional_id: s.professional_id, branch_id: branchId, service_id: serviceId, start_at: s.start_at, session_key: sessionKey }),
    onSuccess: (h, s) => { setHold(h); setSlot(s); },
    onError: (e) => { toast.error(errorMessage(e)); setSlot(null); },
  });

  const book = useMutation({
    mutationFn: () => publicBooking.book(slug, {
      hold_id: hold!.id, session_key: sessionKey,
      customer: { full_name: details.full_name, mobile: details.mobile || undefined, email: details.email || undefined, whatsapp_opt_in: whatsappOptIn },
      customer_notes: details.notes || undefined, dependent_id: dependentId || undefined,
      form_answers: bookingForm.data ? answers : undefined, coupon_code: coupon ?? undefined,
    }),
    onSuccess: (appt) => {
      try { window.localStorage.setItem(`ap.appt.${appt.reference}`, appt.access_token ?? ""); } catch { /* ignore */ }
      router.push(`/o/${slug}/appointments/${appt.reference}${appt.access_token ? `?t=${appt.access_token}` : ""}`);
    },
    onError: (e) => { const fe = formErrorsFromApi(e); if (fe) { setFormErrors(fe); toast.error("Please check the highlighted answers."); } else toast.error(errorMessage(e)); },
  });

  const onExpire = useCallback(() => { toast.warning("Your slot hold expired. Please choose a time again."); setHold(null); setSlot(null); }, []);

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div className="space-y-6">
        <ol className="flex flex-wrap gap-2 text-xs">
          {STEPS.map((label, i) => (
            <li key={label} className={cn("flex items-center gap-1.5 rounded-full border px-3 py-1", i < step && "border-primary/40 bg-accent text-accent-foreground", i === step && "border-primary bg-primary text-primary-foreground")}>
              {i < step ? <Check className="size-3" /> : <span className="font-semibold">{i + 1}</span>} {label}
            </li>
          ))}
        </ol>

        {step === 0 ? (
          <Section title="Choose a service">
            {services.isLoading ? <Skeleton className="h-40" /> : (
              <div className="grid gap-3 sm:grid-cols-2">
                {services.data?.map((s) => (
                  <button key={s.id} data-testid="pick-service" onClick={() => setServiceId(s.id)} className="rounded-xl border p-4 text-left transition-colors hover:border-primary hover:bg-accent/40">
                    <p className="font-medium">{s.name}</p>
                    <p className="text-sm text-muted-foreground">{s.duration_minutes} min · {s.payment_mode === "free" ? "Free" : formatPaise(s.discounted_price_paise ?? s.price_paise)}</p>
                  </button>
                ))}
              </div>
            )}
          </Section>
        ) : null}

        {step === 1 ? (
          <Section title="Choose a location" onBack={() => setServiceId(null)}>
            <div className="grid gap-3 sm:grid-cols-2">
              {data.branches.map((b) => {
                const a = (b.address ?? {}) as Record<string, string>;
                return (
                  <button key={b.id} data-testid="pick-branch" onClick={() => setBranchId(b.id)} className="rounded-xl border p-4 text-left transition-colors hover:border-primary hover:bg-accent/40">
                    <p className="font-medium">{b.name}</p>
                    <p className="flex items-center gap-1 text-sm text-muted-foreground"><MapPin className="size-3.5" />{[a.line1, a.city].filter(Boolean).join(", ") || "Address on request"}</p>
                  </button>
                );
              })}
            </div>
          </Section>
        ) : null}

        {step === 2 ? (
          <Section title="Choose a professional" onBack={() => (data.branches.length > 1 ? setBranchId(null) : setServiceId(null))}>
            {professionals.isLoading ? <Skeleton className="h-32" /> : professionals.data?.length === 0 ? (
              <Alert variant="info"><AlertDescription>No professional offers this service at this location yet. Choose another location or service.</AlertDescription></Alert>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {(professionals.data?.length ?? 0) > 1 && data.settings.booking?.allow_any_professional !== false ? (
                  <button data-testid="pick-any" onClick={() => setProfessionalId("any")} className="rounded-xl border border-dashed p-4 text-left hover:border-primary hover:bg-accent/40">
                    <p className="font-medium">Any available professional</p><p className="text-sm text-muted-foreground">See every free slot.</p>
                  </button>
                ) : null}
                {professionals.data?.map((p) => (
                  <button key={p.id} data-testid="pick-professional" onClick={() => setProfessionalId(p.id)} className="flex gap-3 rounded-xl border p-4 text-left hover:border-primary hover:bg-accent/40">
                    <span className="grid size-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground"><UserRound className="size-4" /></span>
                    <span><span className="block font-medium">{p.display_name}</span><span className="block text-sm text-muted-foreground">{p.specialization}</span></span>
                  </button>
                ))}
              </div>
            )}
          </Section>
        ) : null}

        {step === 3 && serviceId && branchId ? (
          <Section title="Pick a date and time" onBack={() => setProfessionalId(null)}>
            {reserve.isPending ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Reserving your slot…</p> : null}
            <SlotPicker
              serviceId={serviceId}
              branchId={branchId}
              professionalId={professionalId === "any" ? undefined : professionalId ?? undefined}
              fetchDay={(p) => publicBooking.availability(slug, p)}
              fetchSummary={(p) => publicBooking.summary(slug, p)}
              selected={slot}
              onSelect={(s, day) => { setTz(day.timezone); reserve.mutate(s); }}
            />
          </Section>
        ) : null}

        {step === 4 && hold ? (
          <Section title="Your details" onBack={releaseHold} badge={<HoldCountdown expiresAt={hold.expires_at} onExpire={onExpire} />}>
            {!user && data.settings.booking?.allow_guest_booking === false ? (
              <Alert variant="info"><AlertDescription>This clinic asks you to <Link className="font-medium underline" href={`/login?next=${encodeURIComponent(`/o/${slug}/book?service=${serviceId}`)}`}>sign in</Link> before booking.</AlertDescription></Alert>
            ) : null}
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); book.mutate(); }} data-testid="details-form">
              <Field label="Full name" htmlFor="bk_name" className="sm:col-span-2"><Input id="bk_name" required minLength={2} value={details.full_name} onChange={(e) => setDetails({ ...details, full_name: e.target.value })} /></Field>
              <Field label="Mobile number" htmlFor="bk_mobile"><Input id="bk_mobile" inputMode="tel" required={!user?.mobile && !details.email} value={details.mobile} onChange={(e) => setDetails({ ...details, mobile: e.target.value })} /></Field>
              <Field label="Email (optional)" htmlFor="bk_email"><Input id="bk_email" type="email" value={details.email} onChange={(e) => setDetails({ ...details, email: e.target.value })} /></Field>
              {data.settings.messaging?.whatsapp_enabled ? (
                <label className="flex items-start gap-2 text-sm sm:col-span-2">
                  <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={whatsappOptIn} onChange={(e) => setWhatsappOptIn(e.target.checked)} data-testid="whatsapp-opt-in" />
                  <span>Send booking updates and reminders to my mobile on WhatsApp</span>
                </label>
              ) : null}
              {user && dependents.data?.length ? (
                <Field label="Booking for" htmlFor="bk_for" className="sm:col-span-2">
                  <select id="bk_for" className="h-10 w-full rounded-lg border px-3 text-sm" value={dependentId} onChange={(e) => setDependentId(e.target.value)}>
                    <option value="">Myself</option>
                    {dependents.data.map((d) => <option key={d.id} value={d.id}>{d.full_name} ({d.relationship_label})</option>)}
                  </select>
                </Field>
              ) : null}
              <Field label="Anything the professional should know? (optional)" htmlFor="bk_notes" className="sm:col-span-2"><Textarea id="bk_notes" value={details.notes} onChange={(e) => setDetails({ ...details, notes: e.target.value })} /></Field>
              {bookingForm.data ? (
                <div className="space-y-3 rounded-xl border p-4 sm:col-span-2" data-testid="booking-form-section">
                  <div><p className="font-medium">{bookingForm.data.name}</p>{bookingForm.data.instructions ? <p className="text-sm text-muted-foreground">{bookingForm.data.instructions}</p> : null}</div>
                  <DynamicForm fields={bookingForm.data.fields} answers={answers} onChange={(a) => { setAnswers(a); setFormErrors({}); }} errors={formErrors} uploadFile={(file) => publicForms.uploadFile(slug, file)} />
                </div>
              ) : null}
              {!user ? <p className="text-xs text-muted-foreground sm:col-span-2">Already have an account? <Link className="underline" href={`/login?next=${encodeURIComponent(`/o/${slug}/book?service=${serviceId}`)}`}>Sign in</Link> to see this booking in your dashboard.</p> : null}
              <Button type="submit" size="lg" className="sm:col-span-2" disabled={book.isPending}>{book.isPending ? <Loader2 className="animate-spin" /> : null} Confirm booking</Button>
            </form>
          </Section>
        ) : null}
      </div>

      <Card className="h-fit lg:sticky lg:top-24">
        <CardHeader><CardTitle>Summary</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="Organization" value={data.organization.name} />
          <Row label="Service" value={service?.name ?? "—"} />
          <Row label="Location" value={data.branches.find((b) => b.id === branchId)?.name ?? "—"} />
          <Row label="Professional" value={slot ? professionals.data?.find((p) => p.id === slot.professional_id)?.display_name ?? "Any" : professionalId && professionalId !== "any" ? professionals.data?.find((p) => p.id === professionalId)?.display_name ?? "—" : professionalId === "any" ? "Any available" : "—"} />
          <Row label="Time" value={slot ? `${formatDateLong(slot.start_at, tz)} · ${formatTime(slot.start_at, tz)}` : "—"} />
          {service ? <Row label="Duration" value={<span className="flex items-center gap-1"><Clock className="size-3.5" /> {service.duration_minutes} min</span>} /> : null}
          {quote.data ? (
            <div className="space-y-1 rounded-lg bg-muted/50 p-3">
              <Row label="Price" value={quote.data.total_amount_paise === 0 ? "Free" : formatPaise(quote.data.total_amount_paise)} />
              {quote.data.discount_paise ? <Row label="Discount" value={`− ${formatPaise(quote.data.discount_paise)}`} /> : null}
              {quote.data.tax_paise ? <Row label="Tax" value={formatPaise(quote.data.tax_paise)} /> : null}
              <Row label="Pay now" value={<strong data-testid="pay-now">{quote.data.advance_due_paise === 0 ? "Nothing" : formatPaise(quote.data.advance_due_paise)}</strong>} />
              <p className="pt-1 text-xs text-muted-foreground">{quote.data.advance_due_paise === 0 ? "Pay at the clinic." : "Paid by UPI to the clinic's own account after booking. The clinic confirms once the payment is verified."}</p>
            </div>
          ) : null}
          {quote.isError && coupon ? <p className="text-xs text-destructive" data-testid="coupon-error">{errorMessage(quote.error)} <button type="button" className="underline" onClick={() => { setCoupon(null); setCouponInput(""); }}>Remove</button></p> : null}
          {serviceId && branchId && quote.data?.payment_mode !== "free" ? (
            coupon && !quote.isError ? (
              <p className="flex items-center justify-between text-xs"><span className="text-success">Coupon <b className="font-mono">{coupon}</b> applied</span><button type="button" className="underline" onClick={() => { setCoupon(null); setCouponInput(""); }}>Remove</button></p>
            ) : (
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (couponInput.trim()) setCoupon(couponInput.trim().toUpperCase()); }}>
                <Input aria-label="Coupon code" placeholder="Coupon code" className="h-8 font-mono uppercase" value={couponInput} onChange={(e) => setCouponInput(e.target.value)} />
                <Button type="submit" size="sm" variant="outline">Apply</Button>
              </form>
            )
          ) : null}
          {hold ? <Badge variant="success" className="w-full justify-center">Slot reserved</Badge> : null}
        </CardContent>
      </Card>
    </div>
  );
}

function Section({ title, children, onBack, badge }: { title: string; children: React.ReactNode; onBack?: () => void; badge?: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {onBack ? <Button type="button" size="icon" variant="ghost" onClick={onBack} aria-label="Back"><ArrowLeft /></Button> : null}
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        </div>
        {badge}
      </div>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="flex items-start justify-between gap-3"><span className="text-muted-foreground">{label}</span><span className="text-right font-medium">{value}</span></div>;
}
