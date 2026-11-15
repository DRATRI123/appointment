"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, CalendarDays, Check, ChevronUp, Clock, CreditCard, Loader2, MapPin, Pencil, ShieldCheck, Stethoscope, TicketPercent, TimerReset, UserRound } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { publicCatalog } from "@/services/catalog";
import { bookingSessionKey, publicBooking } from "@/services/booking";
import { customerSelfService, publicForms } from "@/services/customers";
import { formErrorsFromApi, type Answers } from "@/components/forms/dynamic-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { parseBookingParams, matchHint } from "@/lib/booking-params";
import { errorMessage } from "@/lib/errors";
import { cn, formatPaise } from "@/lib/utils";
import { useBooking, addressLine } from "./booking-shell";
import { BranchStep, DoctorStep, DoctorAvatar, ServiceStep, EmptyChoice } from "./steps";
import { TimePicker } from "./time-picker";
import { DetailsStep, digitsOnly, type Details } from "./details-step";
import type { Hold, Slot } from "@/types/booking";

type StepKey = "service" | "branch" | "doctor" | "time" | "details" | "review";
const TITLES: Record<StepKey, { title: string; short: string }> = {
  service: { title: "What would you like to book?", short: "Service" },
  branch: { title: "Choose a location", short: "Location" },
  doctor: { title: "Choose your doctor", short: "Doctor" },
  time: { title: "Pick a date and time", short: "Date & time" },
  details: { title: "Your details", short: "Details" },
  review: { title: "Review and confirm", short: "Confirm" },
};

/** "98123 00001" / "098123..." / "+91 98123..." -> "+919812300001" (Indian default), mirroring the server. */
export function e164(raw: string): string {
  const v = digitsOnly(raw);
  if (/^[6-9]\d{9}$/.test(v)) return `+91${v}`;
  if (/^0[6-9]\d{9}$/.test(v)) return `+91${v.slice(1)}`;
  return v.startsWith("+") ? v : `+${v}`;
}

function dateTimeLabel(iso: string, tz: string) {
  const d = new Date(iso);
  return {
    date: new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: tz }).format(d),
    time: new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: tz }).format(d),
  };
}

export function BookingFlow() {
  const { slug, data, base } = useBooking();
  const router = useRouter();
  const params = useSearchParams();
  const hints = useMemo(() => parseBookingParams(params), [params]);
  const { user } = useAuth();
  const sessionKey = useMemo(() => (typeof window === "undefined" ? "" : bookingSessionKey()), []);
  const booking = data.settings.booking ?? {};
  const tz = data.organization.timezone;

  // Each choice is `undefined` until the visitor makes it; until then a matching URL hint (or the only option) is used.
  // Going back sets an explicit `null`, so a hint never overrides what the visitor did.
  const [branchSel, setBranchId] = useState<string | null | undefined>(undefined);
  const [serviceSel, setServiceSel] = useState<string | null | undefined>(undefined);
  const [doctorSel, setDoctorSel] = useState<string | null | undefined>(undefined);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [hold, setHold] = useState<Hold | null>(null);
  const [draft, setDraft] = useState<Partial<Details>>({});
  const [detailsDone, setDetailsDone] = useState(false);
  const [verified, setVerified] = useState<{ mobile: string; token: string } | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [coupon, setCoupon] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);

  // Signed-in customers get their own details pre-filled; whatever they type wins.
  const details: Details = {
    full_name: draft.full_name ?? user?.full_name ?? "", mobile: draft.mobile ?? user?.mobile ?? "", email: draft.email ?? user?.email ?? "",
    notes: draft.notes ?? "", whatsapp: draft.whatsapp ?? false, dependentId: draft.dependentId ?? "",
  };

  // Order: service → doctor → location. A location preselected by the link (or the only one) narrows the lists early.
  const presetBranch = matchHint(data.branches, hints.branch)?.id ?? (data.branches.length === 1 ? data.branches[0].id : undefined);
  const services = useQuery({ queryKey: ["pb-services", slug, presetBranch ?? null], queryFn: () => publicCatalog.services(slug, { branch_id: presetBranch }) });
  const serviceId = serviceSel !== undefined ? serviceSel : matchHint(services.data, hints.service)?.id ?? null;
  const professionals = useQuery({
    queryKey: ["pb-pros", slug, presetBranch ?? null, serviceId],
    queryFn: () => publicCatalog.professionals(slug, { branch_id: presetBranch, service_id: serviceId ?? undefined }),
    enabled: !!serviceId,
  });
  const proList = useMemo(() => professionals.data ?? [], [professionals.data]);
  const doctor = doctorSel !== undefined ? doctorSel : matchHint(proList, hints.doctor)?.id ?? (proList.length === 1 ? proList[0].id : null);
  // Locations where the chosen doctor (or, for "first available", any doctor offering the service) works.
  const branchChoices = useMemo(() => {
    const pros = doctor && doctor !== "any" ? proList.filter((p) => p.id === doctor) : proList;
    const ids = new Set(pros.flatMap((p) => (p.branches ?? []).filter((b) => b.is_active !== false).map((b) => b.branch_id)));
    return data.branches.filter((b) => ids.has(b.id));
  }, [doctor, proList, data.branches]);
  const branchHint = matchHint(branchChoices, hints.branch)?.id;
  const branchId = branchSel !== undefined ? branchSel : branchHint ?? (branchChoices.length === 1 ? branchChoices[0].id : null);
  const setServiceId = (id: string | null) => { setServiceSel(id); setDoctorSel(undefined); setBranchId(undefined); };
  const setDoctor = (id: string | null) => { setDoctorSel(id); setBranchId(undefined); };
  const quote = useQuery({
    queryKey: ["pb-quote", slug, serviceId, branchId, slot?.professional_id, coupon],
    queryFn: () => publicBooking.quote(slug, { service_id: serviceId!, branch_id: branchId!, professional_id: slot?.professional_id, coupon_code: coupon ?? undefined }),
    enabled: !!serviceId && !!branchId,
    retry: false,
  });
  const bookingForm = useQuery({ queryKey: ["pb-form", slug, serviceId, branchId], queryFn: () => publicForms.form(slug, { service_id: serviceId!, branch_id: branchId! }), enabled: !!serviceId && !!branchId });
  const dependents = useQuery({ queryKey: ["pb-dependents", data.organization.id], queryFn: () => customerSelfService.dependents(data.organization.id), enabled: !!user, retry: false });

  const service = services.data?.find((s) => s.id === serviceId) ?? null;
  const branch = data.branches.find((b) => b.id === branchId) ?? null;
  const chosenPro = proList.find((p) => p.id === (slot?.professional_id ?? doctor)) ?? null;

  const verificationRequired = useMemo(() => {
    if (booking.require_mobile_verification === false) return false;
    if (user?.mobile && user.mobile_verified_at && details.mobile && e164(details.mobile) === user.mobile) return false;
    return true;
  }, [booking.require_mobile_verification, user, details.mobile]);

  const steps: StepKey[] = ["service", ...(proList.length === 1 ? [] : (["doctor"] as const)), ...(branchChoices.length > 1 ? (["branch"] as const) : []), "time", "details", "review"];
  const current: StepKey = !serviceId ? "service" : doctor === null ? "doctor" : !branchId ? "branch" : !hold ? "time" : !detailsDone ? "details" : "review";
  const index = steps.indexOf(current);

  useEffect(() => {
    // Keep the active step in view on phones after each choice.
    if (index > 0) top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [index]);

  const release = useCallback(async () => {
    if (hold) {
      try { await publicBooking.releaseHold(slug, hold.id, sessionKey); } catch { /* it expires on its own */ }
    }
    setHold(null);
    setSlot(null);
    setDetailsDone(false);
    setVerified(null);
  }, [hold, slug, sessionKey]);

  const reserve = useMutation({
    mutationFn: (s: Slot) => publicBooking.hold(slug, { professional_id: s.professional_id, branch_id: branchId, service_id: serviceId, start_at: s.start_at, session_key: sessionKey }),
    onSuccess: (h, s) => { setHold(h); setSlot(s); setVerified(null); setDetailsDone(false); },
    onError: (e) => toast.error(e instanceof ApiError && e.status === 409 ? "Someone just booked that time. Please choose another." : errorMessage(e)),
  });

  const book = useMutation({
    mutationFn: () => publicBooking.book(slug, {
      hold_id: hold!.id, session_key: sessionKey, mobile_verification_token: verified?.token,
      customer: { full_name: details.full_name.trim(), mobile: details.mobile ? e164(details.mobile) : undefined, email: details.email.trim() || undefined, whatsapp_opt_in: details.whatsapp },
      customer_notes: details.notes.trim() || undefined, dependent_id: details.dependentId || undefined,
      form_answers: bookingForm.data ? answers : undefined, coupon_code: coupon ?? undefined,
    }),
    onSuccess: (appt) => {
      try { window.localStorage.setItem(`ap.appt.${appt.reference}`, appt.access_token ?? ""); } catch { /* private mode */ }
      router.push(`${base}/appointments/${appt.reference}${appt.access_token ? `?t=${encodeURIComponent(appt.access_token)}` : ""}`);
    },
    onError: (e) => {
      const fe = formErrorsFromApi(e);
      const code = e instanceof ApiError ? e.code : "";
      if (fe) { setFormErrors(fe); setDetailsDone(false); toast.error("Please check the highlighted answers."); return; }
      if (code === "mobile_not_verified" || code === "mobile_verification_expired") { setVerified(null); setDetailsDone(false); toast.error(errorMessage(e)); return; }
      if (["hold_expired", "slot_unavailable", "hold_not_found"].includes(code)) { setHold(null); setSlot(null); setDetailsDone(false); toast.error("That time is no longer available. Please choose another."); return; }
      toast.error(errorMessage(e));
    },
  });

  const onExpire = useCallback(() => {
    toast.warning("Your reserved time expired. Please choose a time again.");
    setHold(null); setSlot(null); setDetailsDone(false); setVerified(null);
  }, []);

  const back = async () => {
    if (current === "review") return setDetailsDone(false);
    if (current === "details") return release();
    if (current === "time") {
      if (branchChoices.length > 1) return setBranchId(null);
      if (proList.length > 1) return setDoctor(null);
      return setServiceId(null);
    }
    if (current === "branch") return proList.length > 1 ? setDoctor(null) : setServiceId(null);
    if (current === "doctor") return setServiceId(null);
  };

  const when = slot ? dateTimeLabel(slot.start_at, tz) : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]" ref={top}>
      <div className="min-w-0 space-y-6 pb-28 lg:pb-0">
        <Stepper steps={steps} index={index} />
        <section key={current} className="pb-enter space-y-5" aria-labelledby="step-title">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {index > 0 ? <Button type="button" size="icon" variant="ghost" className="-ml-2 rounded-full" onClick={back} aria-label="Back"><ArrowLeft /></Button> : null}
              <h2 id="step-title" className="text-2xl font-semibold tracking-tight">{TITLES[current].title}</h2>
            </div>
            {hold && (current === "details" || current === "review") ? <HoldTimer expiresAt={hold.expires_at} onExpire={onExpire} /> : null}
          </div>

          {current === "service" ? (
            services.isLoading ? <CardsSkeleton /> : services.isError ? <EmptyChoice text="We couldn't load the services. Please refresh the page." /> : (
              <ServiceStep services={services.data ?? []} categories={data.categories} selected={serviceId} branchId={branchId} onSelect={(s) => setServiceId(s.id)} />
            )
          ) : null}

          {current === "branch" ? <BranchStep branches={branchChoices} selected={branchId} onSelect={(b) => setBranchId(b.id)} /> : null}

          {current === "doctor" ? (
            professionals.isLoading ? <CardsSkeleton /> : (
              <DoctorStep professionals={proList} allowAny={booking.allow_any_professional !== false} selected={doctor} onSelect={setDoctor} />
            )
          ) : null}

          {current === "time" && serviceId && branchId ? (
            <TimePicker slug={slug} serviceId={serviceId} branchId={branchId} professionalId={doctor === "any" ? undefined : doctor ?? undefined}
              initialDate={hints.date} busy={reserve.isPending} selected={slot} onSelect={(s) => reserve.mutate(s)} />
          ) : null}
          {current === "time" && reserve.isPending ? <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="size-4 animate-spin" />Reserving your time…</p> : null}

          {current === "details" && hold ? (
            <DetailsStep slug={slug} holdId={hold.id} sessionKey={sessionKey} details={details} onChange={setDraft}
              verificationRequired={verificationRequired} verifiedFor={verified?.mobile ?? null} onVerified={(mobile, token) => setVerified({ mobile, token })}
              whatsappEnabled={!!data.settings.messaging?.whatsapp_enabled} dependents={dependents.data ?? []}
              form={bookingForm.data} answers={answers} onAnswers={(a) => { setAnswers(a); setFormErrors({}); }} formErrors={formErrors}
              onContinue={() => setDetailsDone(true)} />
          ) : null}

          {current === "review" && hold && slot && service && branch && when ? (
            <div className="space-y-5" data-testid="review">
              <div className="divide-y rounded-2xl border bg-card">
                <ReviewRow icon={Stethoscope} label="Service" value={`${service.name} · ${service.duration_minutes} min`} onEdit={() => { void release(); setServiceId(null); }} />
                <ReviewRow icon={UserRound} label="Doctor" value={chosenPro?.display_name ?? "First available"} onEdit={proList.length > 1 ? () => { void release(); setDoctor(null); } : undefined} />
                <ReviewRow icon={CalendarDays} label="Date & time" value={`${when.date}, ${when.time}`} onEdit={() => void release()} />
                <ReviewRow icon={MapPin} label="Location" value={[branch.name, addressLine(branch.address)].filter(Boolean).join(" · ")} />
                <ReviewRow icon={ShieldCheck} label="Patient" value={`${details.full_name} · ${e164(details.mobile)}${details.email ? ` · ${details.email}` : ""}`} onEdit={() => setDetailsDone(false)} />
              </div>
              <PriceBlock quote={quote.data} loading={quote.isLoading} error={quote.isError && coupon ? errorMessage(quote.error) : null} coupon={coupon} onCoupon={setCoupon} free={service.payment_mode === "free"} />
              <Policy cancellation={data.settings.cancellation ?? {}} />
              <Button size="lg" className="h-12 w-full text-base" onClick={() => book.mutate()} disabled={book.isPending || (quote.isError && !!coupon)} data-testid="confirm-booking">
                {book.isPending ? <Loader2 className="animate-spin" /> : <Check />} Confirm booking{quote.data && quote.data.advance_due_paise > 0 ? ` · pay ${formatPaise(quote.data.advance_due_paise)} next` : ""}
              </Button>
              <p className="text-center text-xs text-muted-foreground">By confirming you agree to the clinic&apos;s cancellation policy above.</p>
            </div>
          ) : null}
        </section>
      </div>

      <Summary service={service} branch={branch} pro={chosenPro} anyDoctor={doctor === "any" && !slot} when={when} quote={quote.data} />
    </div>
  );
}

// -------------------------------------------------------------------------------------------------- pieces
function Stepper({ steps, index }: { steps: StepKey[]; index: number }) {
  return (
    <nav aria-label="Booking progress">
      <p className="mb-2 text-sm text-muted-foreground sm:hidden">Step {index + 1} of {steps.length} · {TITLES[steps[index]].short}</p>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted sm:hidden" aria-hidden><div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${((index + 1) / steps.length) * 100}%` }} /></div>
      <ol className="hidden items-center gap-2 sm:flex">
        {steps.map((s, i) => (
          <li key={s} className="flex items-center gap-2" aria-current={i === index ? "step" : undefined}>
            <span className={cn("flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
              i < index && "bg-accent text-accent-foreground", i === index && "bg-primary text-primary-foreground shadow-sm", i > index && "text-muted-foreground")}>
              {i < index ? <Check className="size-3.5" aria-hidden /> : <span className="tabular-nums">{i + 1}</span>} {TITLES[s].short}
            </span>
            {i < steps.length - 1 ? <span className="h-px w-4 bg-border" aria-hidden /> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function HoldTimer({ expiresAt, onExpire }: { expiresAt: string; onExpire: () => void }) {
  const [left, setLeft] = useState(() => Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)));
  useEffect(() => {
    const id = setInterval(() => {
      const next = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
      setLeft(next);
      if (next === 0) { clearInterval(id); onExpire(); }
    }, 1000);
    return () => clearInterval(id);
  }, [expiresAt, onExpire]);
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium tabular-nums", left < 60 ? "bg-destructive/10 text-destructive-ink" : "bg-accent text-accent-foreground")} data-testid="hold-countdown" role="timer" aria-live={left < 60 ? "polite" : "off"}>
      <TimerReset className="size-3.5" aria-hidden /> Time held for {String(Math.floor(left / 60)).padStart(2, "0")}:{String(left % 60).padStart(2, "0")}
    </span>
  );
}

function ReviewRow({ icon: Icon, label, value, onEdit }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; onEdit?: () => void }) {
  return (
    <div className="flex items-start gap-3 p-4">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="font-medium break-words">{value}</p>
      </div>
      {onEdit ? <Button type="button" variant="ghost" size="sm" className="h-8 shrink-0" onClick={onEdit}><Pencil className="size-3.5" aria-hidden /> Change<span className="sr-only"> {label}</span></Button> : null}
    </div>
  );
}

function PriceBlock({ quote, loading, error, coupon, onCoupon, free }: {
  quote: import("@/types/booking").PriceQuote | undefined; loading: boolean; error: string | null; coupon: string | null; onCoupon: (c: string | null) => void; free: boolean;
}) {
  const [input, setInput] = useState("");
  if (loading) return <Skeleton className="h-28 rounded-2xl" />;
  return (
    <div className="space-y-3 rounded-2xl border bg-card p-4" data-testid="price-block">
      {quote ? (
        <dl className="space-y-1.5 text-sm">
          <Line label="Consultation fee" value={quote.total_amount_paise === 0 ? "Free" : formatPaise(quote.subtotal_paise)} />
          {quote.discount_paise ? <Line label="Discount" value={`− ${formatPaise(quote.discount_paise)}`} /> : null}
          {quote.tax_paise ? <Line label="Tax" value={formatPaise(quote.tax_paise)} /> : null}
          <Line label="Total" value={quote.total_amount_paise === 0 ? "Free" : formatPaise(quote.total_amount_paise)} strong />
          <div className="mt-2 flex items-start gap-2 rounded-xl bg-muted/60 p-3 text-sm">
            <CreditCard className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <p>
              {quote.advance_due_paise === 0
                ? (quote.total_amount_paise === 0 ? "No payment needed." : "Nothing to pay now. Pay at the clinic.")
                : <><span className="font-semibold" data-testid="pay-now">Pay {formatPaise(quote.advance_due_paise)} now</span> by UPI straight to the clinic&apos;s own account. Your booking is confirmed once the clinic sees the payment.</>}
            </p>
          </div>
        </dl>
      ) : null}
      {!free ? (
        coupon && !error ? (
          <p className="flex items-center justify-between text-sm"><span className="flex items-center gap-1.5 text-success-ink"><TicketPercent className="size-4" aria-hidden />Coupon <b className="font-mono">{coupon}</b> applied</span><button type="button" className="text-xs underline" onClick={() => { onCoupon(null); setInput(""); }}>Remove</button></p>
        ) : (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (input.trim()) onCoupon(input.trim().toUpperCase()); }}>
            <Input aria-label="Coupon code" placeholder="Have a coupon?" className="h-10 font-mono uppercase placeholder:font-sans placeholder:normal-case" value={input} onChange={(e) => setInput(e.target.value)} maxLength={32} />
            <Button type="submit" variant="outline" className="h-10">Apply</Button>
          </form>
        )
      ) : null}
      {error ? <p className="text-sm text-destructive-ink" role="alert" data-testid="coupon-error">{error} <button type="button" className="underline" onClick={() => { onCoupon(null); setInput(""); }}>Remove coupon</button></p> : null}
    </div>
  );
}

function Line({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return <div className={cn("flex justify-between gap-3", strong && "border-t pt-2 text-base font-semibold")}><dt className={strong ? "" : "text-muted-foreground"}>{label}</dt><dd className="tabular-nums">{value}</dd></div>;
}

function Policy({ cancellation }: { cancellation: Record<string, unknown> }) {
  const canCancel = cancellation.customer_can_cancel !== false;
  const hours = Number(cancellation.cancel_before_hours ?? 0);
  const canMove = cancellation.customer_can_reschedule !== false;
  return (
    <div className="rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">Changes and cancellation</p>
      <p>
        {canCancel ? `You can cancel online up to ${hours} hour${hours === 1 ? "" : "s"} before the appointment.` : "To cancel, please contact the clinic."}{" "}
        {canMove ? "You can also move it to another time from your confirmation page." : ""}
      </p>
    </div>
  );
}

function Summary({ service, branch, pro, anyDoctor, when, quote }: {
  service: import("@/types/catalog").Service | null; branch: import("@/types/catalog").Branch | null; pro: import("@/types/catalog").Professional | null;
  anyDoctor: boolean; when: { date: string; time: string } | null; quote: import("@/types/booking").PriceQuote | undefined;
}) {
  const [open, setOpen] = useState(false);
  const price = quote ? (quote.total_amount_paise === 0 ? "Free" : formatPaise(quote.total_amount_paise)) : null;
  const body = (
    <dl className="space-y-3 text-sm">
      <SumRow icon={Stethoscope} label="Service" value={service ? service.name : "Not chosen yet"} muted={!service} />
      <SumRow icon={MapPin} label="Location" value={branch?.name ?? "Not chosen yet"} muted={!branch} />
      <SumRow icon={UserRound} label="Doctor" value={pro ? pro.display_name : anyDoctor ? "First available" : "Not chosen yet"} muted={!pro && !anyDoctor} avatar={pro} />
      <SumRow icon={CalendarDays} label="When" value={when ? `${when.date} · ${when.time}` : "Not chosen yet"} muted={!when} />
      {service ? <SumRow icon={Clock} label="Duration" value={`${service.duration_minutes} minutes`} /> : null}
      {price ? (
        <div className="flex items-center justify-between border-t pt-3 text-base font-semibold"><dt>Total</dt><dd className="tabular-nums" data-testid="summary-total">{price}</dd></div>
      ) : null}
    </dl>
  );
  return (
    <>
      <aside className="hidden h-fit rounded-3xl border bg-card p-6 shadow-sm lg:sticky lg:top-20 lg:block" aria-label="Booking summary">
        <p className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Your appointment</p>
        {body}
      </aside>
      {/* Phones: a compact bar at the bottom that opens the full summary. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 shadow-[0_-8px_24px_-12px_rgb(0_0_0/0.25)] backdrop-blur lg:hidden" data-testid="mobile-summary">
        {open ? <div className="max-h-[50dvh] overflow-y-auto border-b px-4 py-4">{body}</div> : null}
        <button type="button" className="flex w-full items-center gap-3 px-4 py-3 text-left" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold">{service?.name ?? "Book an appointment"}</span>
            <span className="block truncate text-xs text-muted-foreground">{when ? `${when.date} · ${when.time}` : pro?.display_name ?? branch?.name ?? "Choose a service to start"}</span>
          </span>
          {price ? <span className="text-sm font-semibold tabular-nums">{price}</span> : null}
          <ChevronUp className={cn("size-4 shrink-0 transition-transform", !open && "rotate-180")} aria-hidden />
          <span className="sr-only">{open ? "Hide" : "Show"} booking summary</span>
        </button>
      </div>
    </>
  );
}

function SumRow({ icon: Icon, label, value, muted, avatar }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; muted?: boolean; avatar?: import("@/types/catalog").Professional | null }) {
  return (
    // dt/dd must be direct children of the row for screen readers, so the icon sits inside the dt.
    <div className="relative min-w-0 pl-7">
      <dt className="text-xs text-muted-foreground">
        {avatar ? <span className="absolute -left-0.5 top-0" aria-hidden><DoctorAvatar pro={avatar} size="xs" /></span> : <Icon className="absolute left-0 top-0.5 size-4 text-muted-foreground" aria-hidden />}
        {label}
      </dt>
      <dd className={cn("font-medium", muted && "font-normal text-muted-foreground")}>{value}</dd>
    </div>
  );
}

function CardsSkeleton() {
  return <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-32 rounded-2xl" />)}</div>;
}
