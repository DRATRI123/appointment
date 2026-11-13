"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarCheck2, QrCode } from "lucide-react";
import { useOrg } from "../../org-provider";
import { bookingSessionKey, publicBooking } from "@/services/booking";
import { AppointmentSummary } from "@/components/booking/appointment-summary";
import { SlotPicker } from "@/components/booking/slot-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import type { Slot } from "@/types/booking";

export function AppointmentStatusPage({ reference }: { reference: string }) {
  const { slug, data } = useOrg();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const token = useMemo(() => {
    const fromQuery = params.get("t");
    if (fromQuery) return fromQuery;
    try { return window.localStorage.getItem(`ap.appt.${reference}`); } catch { return null; }
  }, [params, reference]);
  const appt = useQuery({ queryKey: ["public-appt", slug, reference, token], queryFn: () => publicBooking.status(slug, reference, token), retry: false });
  const [rescheduling, setRescheduling] = useState(false);
  const sessionKey = useMemo(() => bookingSessionKey(), []);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["public-appt", slug, reference] });

  const cancel = useMutation({
    mutationFn: () => publicBooking.cancel(slug, reference, token, "Cancelled by customer"),
    onSuccess: () => { toast.success("Appointment cancelled"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reschedule = useMutation({
    mutationFn: async (slot: Slot) => {
      const hold = await publicBooking.hold(slug, { professional_id: slot.professional_id, branch_id: appt.data!.branch_id, service_id: appt.data!.service_id, start_at: slot.start_at, session_key: sessionKey });
      return publicBooking.reschedule(slug, reference, token, hold.id, sessionKey);
    },
    onSuccess: () => { toast.success("Appointment moved"); setRescheduling(false); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (appt.isLoading) return <Skeleton className="h-64" />;
  if (appt.isError || !appt.data) {
    return <Alert variant="destructive"><AlertTitle>We could not open this appointment</AlertTitle><AlertDescription>The link may be incomplete. Sign in with the mobile number you booked with to see your appointments.</AlertDescription></Alert>;
  }
  const a = appt.data;
  const due = a.advance_due_paise - a.paid_amount_paise;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-success/15 text-success"><CalendarCheck2 className="size-6" /></span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" data-testid="booking-heading">{a.status === "pending_payment" ? "Slot reserved. Complete the payment to confirm." : a.status === "confirmed" ? "Your appointment is confirmed." : a.status === "cancelled" ? "This appointment was cancelled." : "Appointment details"}</h1>
          <p className="text-sm text-muted-foreground">Reference <span className="font-mono">{a.reference}</span>. Keep this link to manage your booking.</p>
        </div>
      </div>

      <Card>
        <CardContent><AppointmentSummary appt={a} /></CardContent>
      </Card>

      {a.status === "pending_payment" && due > 0 ? (
        <Card className="border-primary/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><QrCode className="size-4" /> Pay by UPI</CardTitle>
            <CardDescription>The UPI QR checkout and payment submission land in Phase 6. Until then {data.organization.name} will confirm your booking once payment is received{a.payment_due_at ? ` (please pay before ${new Date(a.payment_due_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })})` : ""}.</CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {(a.can_cancel || a.can_reschedule) && !rescheduling ? (
        <div className="flex flex-wrap gap-2">
          {a.can_reschedule ? <Button variant="outline" onClick={() => setRescheduling(true)}>Reschedule</Button> : null}
          {a.can_cancel ? <Button variant="ghost" className="text-destructive" onClick={() => { if (confirm("Cancel this appointment?")) cancel.mutate(); }}>Cancel appointment</Button> : null}
        </div>
      ) : null}

      {rescheduling ? (
        <Card>
          <CardHeader><CardTitle>Choose a new time</CardTitle><CardDescription>Your current slot is released once the new one is confirmed.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <SlotPicker serviceId={a.service_id} branchId={a.branch_id} professionalId={a.professional_id} fetchDay={(p) => publicBooking.availability(slug, p)} fetchSummary={(p) => publicBooking.summary(slug, p)} onSelect={(s) => reschedule.mutate(s)} />
            <Button variant="ghost" onClick={() => setRescheduling(false)}>Keep current time</Button>
          </CardContent>
        </Card>
      ) : null}

      <p className="text-sm text-muted-foreground">Need help? Contact {data.organization.name}{data.organization.phone ? ` on ${data.organization.phone}` : ""}. <Link href={`/o/${slug}`} className="underline">Back to booking page</Link>.</p>
    </div>
  );
}
