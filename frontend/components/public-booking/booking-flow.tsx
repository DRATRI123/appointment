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
import { e164, stillVerified, type Verified } from "./contact-verification";
import { rememberCampaign } from "@/lib/campaign";
import { DoctorAvatar } from "./steps";
import { DoctorBrowser, DoctorPhoto, servicesOf } from "./doctor-browser";
import { DoctorDetail } from "./doctor-detail";
import { BottomNav } from "@/components/website/bottom-nav";
import { DetailsStep, type Details } from "./details-step";
import type { Hold, Slot } from "@/types/booking";

type Screen = "browse" | "doctor" | "details" | "review";
const SCREENS: Record<Screen, string> = { browse: "Doctors", doctor: "Date & time", details: "Your details", review: "Confirm" };

export { e164 } from "./contact-verification";

function dateTimeLabel(iso: string, tz: string) {
  const d = new Date(iso);
  return {
    date: new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: tz }).format(d),
    time: new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: tz }).format(d),
  };
}

export function BookingFlow() {
  const { slug, data, base, embedded } = useBooking();
  const router = useRouter();
  const params = useSearchParams();
  const hints = useMemo(() => parseBookingParams(params), [params]);
  const { user } = useAuth();
  const sessionKey = useMemo(() => (typeof window === "undefined" ? "" : bookingSessionKey()), []);
  const booking = data.settings.booking ?? {};
  const tz = data.organization.timezone;

  // Each choice is `undefined` until the visitor makes it; until then a matching URL hint (or the only option) is used.
  // Going back sets an explicit `null`, so a hint never overrides what the visitor did.
  const [doctorSel, setDoctorSel] = useState<string | null | undefined>(undefined);
  const [serviceSel, setServiceSel] = useState<string | null | undefined>(undefined);
  const [branchSel, setBranchSel] = useState<string | null | undefined>(undefined);
  const [picked, setPicked] = useState<Slot | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [hold, setHold] = useState<Hold | null>(null);
  const [draft, setDraft] = useState<Partial<Details>>({});
  const [detailsDone, setDetailsDone] = useState(false);
  const [verified, setVerified] = useState<Verified | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [coupon, setCoupon] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);

  // Signed-in customers get their own details pre-filled; whatever they type wins.
  const details: Details = {
    full_name: draft.full_name ?? user?.full_name ?? "", mobile: draft.mobile ?? user?.mobile ?? "", email: draft.email ?? user?.email ?? "",
    notes: draft.notes ?? "", whatsapp: draft.whatsapp ?? false, dependentId: draft.dependentId ?? "",
  };

  // Catalogue: every bookable doctor and service; choices narrow each other below.
  const servicesQ = useQuery({ queryKey: ["pb-services", slug, null], queryFn: () => publicCatalog.services(slug) });
  const prosQ = useQuery({ queryKey: ["site-pros", slug], queryFn: () => publicCatalog.professionals(slug) });
  const allServices = useMemo(() => servicesQ.data ?? [], [servicesQ.data]);
  const allPros = useMemo(() => prosQ.data ?? [], [prosQ.data]);
  const hintService = matchHint(allServices, hints.service) ?? null;
  const offering = useMemo(() => (hintService ? allPros.filter((p) => servicesOf(p, allServices).some((s) => s.id === hintService.id)) : allPros), [hintService, allPros, allServices]);

  // Doctor: chosen, or from the link, or the only one (for the service in the link).
  const doctor = doctorSel !== undefined ? doctorSel : matchHint(allPros, hints.doctor)?.id ?? (offering.length === 1 ? offering[0].id : null);
  const pro = doctor && doctor !== "any" ? allPros.find((p) => p.id === doctor) ?? null : null;
  const serviceOptions = useMemo(() => (pro ? servicesOf(pro, allServices) : allServices), [pro, allServices]);
  const serviceId = serviceSel !== undefined ? serviceSel : (hintService && serviceOptions.some((s) => s.id === hintService.id) ? hintService.id : serviceOptions.length === 1 ? serviceOptions[0].id : null);
  // Locations where this doctor (or, for "first available", any doctor offering the service) works.
  const branchChoices = useMemo(() => {
    const pros = pro ? [pro] : serviceId ? allPros.filter((p) => servicesOf(p, allServices).some((s) => s.id === serviceId)) : allPros;
    const ids = new Set(pros.flatMap((p) => (p.branches ?? []).filter((b) => b.is_active !== false).map((b) => b.branch_id)));
    return data.branches.filter((b) => ids.has(b.id));
  }, [pro, serviceId, allPros, allServices, data.branches]);
  const branchId = branchSel !== undefined ? branchSel : matchHint(branchChoices, hints.branch)?.id ?? (branchChoices.length === 1 ? branchChoices[0].id : null);
  const browseSkipped = doctorSel === undefined && doctor !== null;

  const choose = {
    doctor: (id: string | null) => { setDoctorSel(id); setServiceSel(undefined); setBranchSel(undefined); setPicked(null); },
    service: (id: string) => { setServiceSel(id); setBranchSel(undefined); setPicked(null); },
    branch: (id: string) => { setBranchSel(id); setPicked(null); },
  };

  const priced = slot ?? picked;
  const quote = useQuery({
    queryKey: ["pb-quote", slug, serviceId, branchId, priced?.professional_id ?? pro?.id, coupon],
    queryFn: () => publicBooking.quote(slug, { service_id: serviceId!, branch_id: branchId!, professional_id: priced?.professional_id ?? pro?.id, coupon_code: coupon ?? undefined }),
    enabled: !!serviceId && !!branchId,
    retry: false,
  });
  const bookingForm = useQuery({ queryKey: ["pb-form", slug, serviceId, branchId], queryFn: () => publicForms.form(slug, { service_id: serviceId!, branch_id: branchId! }), enabled: !!serviceId && !!branchId });
  const dependents = useQuery({ queryKey: ["pb-dependents", data.organization.id], queryFn: () => customerSelfService.dependents(data.organization.id), enabled: !!user, retry: false });

  const service = allServices.find((s) => s.id === serviceId) ?? null;
  const branch = data.branches.find((b) => b.id === branchId) ?? null;
  const chosenPro = allPros.find((p) => p.id === (slot?.professional_id ?? doctor)) ?? null;

  const verification = useQuery({ queryKey: ["pb-verification", slug], queryFn: () => publicBooking.verificationOptions(slug), staleTime: 60_000 });
  const verificationRequired = useMemo(() => {
    if (verification.data && !verification.data.required) return false;
    // A signed-in customer booking with their own, already verified mobile number skips the code (the server agrees).
    if (user?.mobile && user.mobile_verified_at && details.mobile && e164(details.mobile) === user.mobile) return false;
    return true;
  }, [verification.data, user, details.mobile]);

  const current: Screen = doctor === null ? "browse" : !hold ? "doctor" : !detailsDone ? "details" : "review";
  const order: Screen[] = browseSkipped ? ["doctor", "details", "review"] : ["browse", "doctor", "details", "review"];
  const index = order.indexOf(current);

  useEffect(() => {
    // Each screen starts at the top on phones.
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
    onError: (e) => { setPicked(null); toast.error(e instanceof ApiError && e.status === 409 ? "Someone just booked that time. Please choose another." : errorMessage(e)); },
  });

  const book = useMutation({
    mutationFn: () => publicBooking.book(slug, {
      hold_id: hold!.id, session_key: sessionKey, verification_token: verificationRequired && stillVerified(verified, details.mobile, details.email) ? verified?.token : undefined,
      customer: { full_name: details.full_name.trim(), mobile: details.mobile ? e164(details.mobile) : undefined, email: details.email.trim() || undefined, whatsapp_opt_in: details.whatsapp },
      customer_notes: details.notes.trim() || undefined, dependent_id: details.dependentId || undefined,
      form_answers: bookingForm.data ? answers : undefined, coupon_code: coupon ?? undefined,
      attribution: { ...(typeof window === "undefined" ? {} : rememberCampaign(params)), entry: embedded ? "embed" : "website" },
    }, `book:${hold!.id}`),
    onSuccess: (appt) => {
      try { window.localStorage.setItem(`ap.appt.${appt.reference}`, appt.access_token ?? ""); } catch { /* private mode */ }
      router.push(`${base}/appointments/${appt.reference}${appt.access_token ? `?t=${encodeURIComponent(appt.access_token)}` : ""}`);
    },
    onError: (e) => {
      const fe = formErrorsFromApi(e);
      const code = e instanceof ApiError ? e.code : "";
      if (fe) { setFormErrors(fe); setDetailsDone(false); toast.error("Please check the highlighted answers."); return; }
      if (code === "contact_not_verified" || code === "contact_verification_expired") { setVerified(null); setDetailsDone(false); toast.error(errorMessage(e)); return; }
      if (["hold_expired", "slot_unavailable", "hold_not_found"].includes(code)) { setHold(null); setSlot(null); setPicked(null); setDetailsDone(false); toast.error("That time is no longer available. Please choose another."); return; }
      toast.error(errorMessage(e));
    },
  });

  const onExpire = useCallback(() => {
    toast.warning("Your reserved time expired. Please choose a time again.");
    setHold(null); setSlot(null); setPicked(null); setDetailsDone(false); setVerified(null);
  }, []);

  const back = async () => {
    if (current === "review") return setDetailsDone(false);
    if (current === "details") return release();
    if (current === "doctor") return choose.doctor(null);
  };

  const when = slot ? dateTimeLabel(slot.start_at, tz) : null;

  if (current === "browse") {
    return (
      <div ref={top} className="pb-24 md:pb-0">
        <DoctorBrowser slug={slug} clinicName={data.organization.name} base={base} professionals={offering} services={allServices} categories={data.categories}
          loading={prosQ.isLoading || servicesQ.isLoading} allowAny={booking.allow_any_professional !== false} serviceFilter={hintService}
          onPick={(p) => choose.doctor(p.id)} onAny={() => choose.doctor("any")} bookingsHref={`${base}/bookings`} />
        {!embedded ? <BottomNav /> : null}
      </div>
    );
  }

  if (current === "doctor") {
    return (
      <div ref={top}>
        <DoctorDetail slug={slug} pro={pro} doctorCount={offering.length} services={serviceOptions} serviceId={serviceId} onService={choose.service}
          branches={branchChoices} branchId={branchId} onBranch={choose.branch} initialDate={hints.date} picked={picked} onPick={setPicked}
          onBook={() => { if (picked) reserve.mutate(picked); }} booking={reserve.isPending} quote={quote.data} tz={tz}
          onBack={browseSkipped ? null : () => void back()} />
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]" ref={top}>
      <div className="min-w-0 space-y-6 pb-28 lg:pb-0">
        <ScreenHeader title={SCREENS[current]} step={index + 1} of={order.length} onBack={() => void back()}
          right={hold ? <HoldTimer expiresAt={hold.expires_at} onExpire={onExpire} /> : null} />
        <section key={current} className="pb-enter space-y-5">
          {current === "details" && hold ? (
            <div className="rounded-3xl bg-white p-5 shadow-[0_8px_30px_-14px_rgb(0_0_0/0.18)] ring-1 ring-black/5 sm:p-7">
            <DetailsStep slug={slug} holdId={hold.id} sessionKey={sessionKey} details={details} onChange={setDraft}
              verificationRequired={verificationRequired} verification={verification.data} verified={verified} onVerified={setVerified}
              whatsappEnabled={!!data.settings.messaging?.whatsapp_enabled} dependents={dependents.data ?? []}
              form={bookingForm.data} answers={answers} onAnswers={(a) => { setAnswers(a); setFormErrors({}); }} formErrors={formErrors}
              onContinue={() => setDetailsDone(true)} />
            </div>
          ) : null}

          {current === "review" && hold && slot && service && branch && when ? (
            <div className="space-y-5" data-testid="review">
              <div className="flex items-center gap-4 rounded-3xl bg-[var(--primary)] p-5 text-[var(--primary-foreground)]">
                {chosenPro ? <DoctorPhoto pro={chosenPro} className="size-16" rounded="rounded-2xl" /> : null}
                <div className="min-w-0">
                  <p className="text-lg font-semibold">{chosenPro?.display_name ?? "Your doctor"}</p>
                  <p className="text-sm">{when.date} · {when.time}</p>
                </div>
              </div>
              <div className="divide-y rounded-3xl border bg-white">
                <ReviewRow icon={Stethoscope} label="Service" value={`${service.name} · ${service.duration_minutes} min`} onEdit={() => void release()} />
                <ReviewRow icon={CalendarDays} label="Date & time" value={`${when.date}, ${when.time}`} onEdit={() => void release()} />
                <ReviewRow icon={MapPin} label="Location" value={[branch.name, addressLine(branch.address)].filter(Boolean).join(" · ")} />
                <ReviewRow icon={ShieldCheck} label="Patient" value={`${details.full_name} · ${e164(details.mobile)}${details.email ? ` · ${details.email}` : ""}`} onEdit={() => setDetailsDone(false)} />
              </div>
              <PriceBlock quote={quote.data} loading={quote.isLoading} error={quote.isError && coupon ? errorMessage(quote.error) : null} coupon={coupon} onCoupon={setCoupon} free={service.payment_mode === "free"} />
              <Policy cancellation={data.settings.cancellation ?? {}} />
              <Button size="lg" className="h-13 w-full rounded-full text-base shadow-[0_10px_24px_-10px_color-mix(in_oklab,var(--primary)_80%,transparent)]" onClick={() => book.mutate()} disabled={book.isPending || (quote.isError && !!coupon)} data-testid="confirm-booking">
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
function ScreenHeader({ title, step, of, onBack, right }: { title: string; step: number; of: number; onBack: () => void; right?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <button type="button" onClick={onBack} aria-label="Back" className="grid size-11 shrink-0 place-items-center rounded-full border border-black/10 bg-white shadow-sm transition-colors hover:bg-gray-50"><ArrowLeft className="size-5" /></button>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Step {step} of {of}</p>
        <h2 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">{title}</h2>
      </div>
      {right}
    </div>
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
      {/* While the summary is open it covers the page: dim the rest so it reads as a panel, and close on tap or Escape. */}
      {open ? <button type="button" aria-label="Close booking summary" className="fixed inset-0 z-20 bg-black/30 lg:hidden" onClick={() => setOpen(false)} data-testid="mobile-summary-backdrop" /> : null}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 shadow-[0_-8px_24px_-12px_rgb(0_0_0/0.25)] backdrop-blur lg:hidden" data-testid="mobile-summary"
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
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
