"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, CalendarClock, CalendarDays, CheckCircle2, Clock, Hourglass, Link2Off, MapPin, Phone, RotateCcw, Stethoscope, UserRound, XCircle } from "lucide-react";
import { bookingSessionKey, publicBooking } from "@/services/booking";
import { publicPayments } from "@/services/payments";
import { UpiCheckout } from "@/components/payments/upi-checkout";
import { JoinAndCalendar } from "@/components/booking/join-and-calendar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { cn, formatPaise } from "@/lib/utils";
import { useBooking } from "./booking-shell";
import { TimePicker } from "./time-picker";
import type { AppointmentDetail, Slot } from "@/types/booking";
import type { Checkout } from "@/types/payment";

type Tone = "success" | "pending" | "action" | "failed";

const TONE: Record<Tone, { ring: string; bg: string; ink: string; icon: React.ComponentType<{ className?: string }> }> = {
  success: { ring: "ring-success/30", bg: "bg-success/15", ink: "text-success-ink", icon: CheckCircle2 },
  pending: { ring: "ring-amber-500/30", bg: "bg-amber-500/15", ink: "text-amber-700 dark:text-amber-300", icon: Hourglass },
  action: { ring: "ring-primary/30", bg: "bg-primary/10", ink: "text-primary", icon: Clock },
  failed: { ring: "ring-destructive/30", bg: "bg-destructive/10", ink: "text-destructive-ink", icon: XCircle },
};

/** Which screen to show, from the appointment and payment state the server reports. */
export function screenFor(a: AppointmentDetail, checkout: Checkout | null | undefined): { tone: Tone; title: string; body: string } {
  const payment = checkout?.payment;
  const due = a.advance_due_paise - a.paid_amount_paise;
  if (a.status === "cancelled") return { tone: "failed", title: "This appointment was cancelled", body: "The time has been released. You're welcome to book again." };
  if (a.status === "expired") return { tone: "failed", title: "This booking expired", body: "Payment wasn't completed in time, so the slot was released. Please book again." };
  if (a.status === "no_show") return { tone: "failed", title: "Marked as missed", body: "The clinic recorded this appointment as missed. Please contact them or book again." };
  if (a.status === "completed") return { tone: "success", title: "Appointment completed", body: "Thank you for visiting. We hope you're feeling better." };
  if (payment?.status === "rejected") return { tone: "failed", title: "Payment not accepted", body: payment.rejection_reason ? `The clinic couldn't match your payment: ${payment.rejection_reason}. Please check and submit again below.` : "The clinic couldn't match your payment. Please check the details and submit again below." };
  if (a.status === "pending_verification" || payment?.status === "submitted" || payment?.status === "under_review") {
    return { tone: "pending", title: "Payment received for checking", body: "Thank you! The clinic confirms your booking once they see the money in their account. This page updates by itself." };
  }
  if (a.status === "pending_payment" && due > 0) return { tone: "action", title: "Almost done: complete your payment", body: `Your time is reserved. Pay ${formatPaise(due)} by UPI below to confirm the booking.` };
  return { tone: "success", title: "Your appointment is confirmed", body: "We've saved your booking. A confirmation is on its way to your phone." };
}

export function AppointmentStatus({ reference }: { reference: string }) {
  const { slug, data, bookPath } = useBooking();
  const params = useSearchParams();
  const pathname = usePathname();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const token = useMemo(() => {
    const fromQuery = params.get("t");
    if (fromQuery) return fromQuery;
    try { return window.localStorage.getItem(`ap.appt.${reference}`); } catch { return null; }
  }, [params, reference]);
  const appt = useQuery({ queryKey: ["pb-appt", slug, reference, token], queryFn: () => publicBooking.status(slug, reference, token), retry: false });
  const checkout = useQuery({
    queryKey: ["pb-checkout", slug, reference, token],
    queryFn: () => publicPayments.checkout(slug, reference, token),
    retry: false,
    enabled: appt.isSuccess,
    refetchInterval: (q) => (q.state.data && ["submitted", "under_review"].includes(q.state.data.payment.status) ? 15_000 : false),
  });
  const [moving, setMoving] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const sessionKey = useMemo(() => bookingSessionKey(), []);
  const refresh = () => Promise.all([queryClient.invalidateQueries({ queryKey: ["pb-appt", slug, reference] }), queryClient.invalidateQueries({ queryKey: ["pb-checkout", slug, reference] })]);

  const cancel = useMutation({
    mutationFn: () => publicBooking.cancel(slug, reference, token, "Cancelled by the patient online"),
    onSuccess: () => { toast.success("Appointment cancelled"); setConfirmCancel(false); void refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reschedule = useMutation({
    mutationFn: async (slot: Slot) => {
      const hold = await publicBooking.hold(slug, { professional_id: slot.professional_id, branch_id: appt.data!.branch_id, service_id: appt.data!.service_id, start_at: slot.start_at, session_key: sessionKey });
      return publicBooking.reschedule(slug, reference, token, hold.id, sessionKey);
    },
    onSuccess: () => { toast.success("Appointment moved"); setMoving(false); void refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (appt.isLoading) return <div className="mx-auto max-w-2xl space-y-4"><Skeleton className="h-36 rounded-3xl" /><Skeleton className="h-56 rounded-3xl" /></div>;
  if (appt.isError || !appt.data) {
    return (
      <div className="pb-enter mx-auto max-w-lg space-y-4 rounded-3xl border bg-card p-8 text-center shadow-sm" role="alert">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-muted"><Link2Off className="size-7 text-muted-foreground" aria-hidden /></span>
        <h1 className="text-2xl font-semibold tracking-tight" data-testid="booking-heading">We couldn&apos;t open this booking</h1>
        <p className="text-muted-foreground">
          {user ? "This booking was not made with your signed-in mobile number or email." : "The link may be incomplete or out of date."} Sign in with a one-time code
          sent to the mobile number or email you booked with to see all your bookings, or contact {data.organization.name}{data.organization.phone ? ` on ${data.organization.phone}` : ""}.
        </p>
        <div className="flex flex-col justify-center gap-2 sm:flex-row">
          {!user ? <Button asChild data-testid="status-sign-in"><Link href={`/login?next=${encodeURIComponent(pathname)}`}>Sign in with code</Link></Button> : null}
          <Button asChild variant={user ? "default" : "outline"}><Link href={bookPath}>Book an appointment</Link></Button>
        </div>
      </div>
    );
  }

  const a = appt.data;
  const screen = screenFor(a, checkout.data);
  const tone = TONE[screen.tone];
  const Icon = tone.icon;
  const start = new Date(a.start_at);
  const date = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: a.timezone }).format(start);
  const time = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: a.timezone }).format(start);
  const closed = ["cancelled", "expired", "no_show", "completed"].includes(a.status);
  const showPayment = checkout.data && !closed && (a.advance_due_paise - a.paid_amount_paise > 0 || checkout.data.payment.status !== "verified");

  return (
    <div className="mx-auto max-w-2xl space-y-6" data-testid="booking-status" data-tone={screen.tone}>
      <section className={cn("pb-enter rounded-3xl border bg-card p-6 text-center shadow-sm ring-4 sm:p-8", tone.ring)} aria-live="polite">
        <span className={cn("pb-pop mx-auto grid size-16 place-items-center rounded-full", tone.bg)}><Icon className={cn("size-8", tone.ink)} aria-hidden /></span>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-balance sm:text-3xl" data-testid="booking-heading">{screen.title}</h1>
        <p className="mx-auto mt-2 max-w-md text-pretty text-muted-foreground">{screen.body}</p>
        <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">Booking reference <span className="font-mono font-medium text-foreground">{a.reference}</span></p>
      </section>

      <section className="pb-enter divide-y rounded-3xl border bg-card shadow-sm" aria-label="Appointment details">
        <Detail icon={Stethoscope} label="Service" value={a.service_name} />
        <Detail icon={UserRound} label="Doctor" value={a.professional_name} />
        <Detail icon={CalendarDays} label="Date" value={date} />
        <Detail icon={Clock} label="Time" value={`${time} (${a.timezone})`} />
        <Detail icon={MapPin} label="Location" value={a.consultation_mode === "online" ? "Online video consultation" : a.branch_name} />
        {a.total_amount_paise > 0 ? <Detail icon={CalendarClock} label="Fee" value={`${formatPaise(a.total_amount_paise)}${a.paid_amount_paise ? ` · ${formatPaise(a.paid_amount_paise)} paid` : ""}`} /> : null}
      </section>

      {!closed ? <JoinAndCalendar appt={a} slug={slug} token={token} organizationName={data.organization.name} /> : null}

      {showPayment && checkout.data ? (
        <UpiCheckout checkout={checkout.data} onSubmit={async (d) => { await publicPayments.submit(slug, reference, token, d); await refresh(); }} />
      ) : null}

      {!closed && (a.can_cancel || a.can_reschedule) && !moving ? (
        <div className="flex flex-wrap gap-2">
          {a.can_reschedule ? <Button variant="outline" onClick={() => setMoving(true)}><RotateCcw /> Reschedule</Button> : null}
          {a.can_cancel ? <Button variant="ghost" className="text-destructive-ink" onClick={() => setConfirmCancel(true)}>Cancel appointment</Button> : null}
        </div>
      ) : null}

      {moving ? (
        <section className="pb-enter space-y-4 rounded-3xl border bg-card p-5 shadow-sm">
          <div><h2 className="text-lg font-semibold">Choose a new time</h2><p className="text-sm text-muted-foreground">Your current time is released only once the new one is confirmed.</p></div>
          <TimePicker slug={slug} serviceId={a.service_id} branchId={a.branch_id} professionalId={a.professional_id} busy={reschedule.isPending} selected={null} onSelect={(s) => reschedule.mutate(s)} />
          <Button variant="ghost" onClick={() => setMoving(false)}>Keep my current time</Button>
        </section>
      ) : null}

      {closed ? <Button asChild size="lg" className="w-full"><Link href={bookPath}>Book again</Link></Button> : null}

      <p className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-center text-sm text-muted-foreground">
        <AlertTriangle className="size-4" aria-hidden /> Keep this page&apos;s link to manage your booking.
        {data.organization.phone ? <a href={`tel:${data.organization.phone}`} className="inline-flex items-center gap-1 font-medium text-foreground hover:underline"><Phone className="size-3.5" aria-hidden />{data.organization.phone}</a> : null}
      </p>

      <Dialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel this appointment?</DialogTitle>
            <DialogDescription>{a.service_name} with {a.professional_name} on {date} at {time}. {a.paid_amount_paise > 0 ? "Any refund is reviewed by the clinic under their policy." : ""}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmCancel(false)}>Keep appointment</Button>
            <Button variant="destructive" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Cancel appointment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Detail({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 px-5 py-3.5">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-wrap justify-between gap-x-4"><span className="text-sm text-muted-foreground">{label}</span><span className="text-right font-medium break-words">{value}</span></div>
    </div>
  );
}
