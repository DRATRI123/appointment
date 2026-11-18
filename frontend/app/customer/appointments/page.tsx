"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarDays } from "lucide-react";
import { customerBooking, publicBooking, bookingSessionKey } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AppointmentSummary } from "@/components/booking/appointment-summary";
import { SlotPicker } from "@/components/booking/slot-picker";
import { errorMessage } from "@/lib/errors";
import type { Appointment, Slot } from "@/types/booking";

export default function CustomerAppointmentsPage() {
  const queryClient = useQueryClient();
  const appts = useQuery({ queryKey: ["my-appointments"], queryFn: customerBooking.mine });
  const [rescheduling, setRescheduling] = useState<Appointment | null>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["my-appointments"] });
  const cancel = useMutation({ mutationFn: (id: string) => customerBooking.cancel(id, "Cancelled by customer"), onSuccess: () => { toast.success("Appointment cancelled"); invalidate(); }, onError: (e) => toast.error(errorMessage(e)) });
  const reschedule = useMutation({
    mutationFn: async ({ appt, slot }: { appt: Appointment; slot: Slot }) => {
      const hold = await publicBooking.hold(appt.organization_slug, { professional_id: slot.professional_id, branch_id: appt.branch_id, service_id: appt.service_id, start_at: slot.start_at, session_key: bookingSessionKey() });
      return customerBooking.reschedule(appt.id, hold.id);
    },
    onSuccess: () => { toast.success("Appointment moved"); setRescheduling(null); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const [now] = useState(() => Date.now());
  const upcoming = (appts.data ?? []).filter((a) => new Date(a.end_at).getTime() >= now && !["cancelled", "expired", "no_show", "completed"].includes(a.status)).sort((a, b) => a.start_at.localeCompare(b.start_at));
  const past = (appts.data ?? []).filter((a) => !upcoming.includes(a));
  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <PageHeader title="My appointments" description="Upcoming and past bookings across every clinic you use, with their status and payment. Open one to pay, reschedule or cancel." />
      {appts.isLoading ? <Skeleton className="h-48" /> : appts.data?.length === 0 ? <EmptyState icon={CalendarDays} title="No appointments yet" body="Bookings made with the mobile number or email you signed in with show up here, from any clinic, even if you booked without signing in." /> : (
        <>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Upcoming</h3>
            {upcoming.length === 0 ? <p className="text-sm text-muted-foreground">Nothing upcoming.</p> : upcoming.map((a) => (
              <Card key={a.id} data-testid="my-appointment">
                <CardHeader><CardTitle className="text-base">{a.organization_name}</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <AppointmentSummary appt={a} />
                  <div className="flex flex-wrap gap-2">
                    <Button asChild size="sm" variant="outline"><Link href={`/${a.organization_slug}/appointments/${a.reference}`}>Open</Link></Button>
                    {a.can_reschedule ? <Button size="sm" variant="outline" onClick={() => setRescheduling(rescheduling?.id === a.id ? null : a)}>Reschedule</Button> : null}
                    {a.can_cancel ? <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm("Cancel this appointment?")) cancel.mutate(a.id); }}>Cancel</Button> : null}
                  </div>
                  {rescheduling?.id === a.id ? <SlotPicker serviceId={a.service_id} branchId={a.branch_id} professionalId={a.professional_id} fetchDay={(p) => publicBooking.availability(a.organization_slug, p)} fetchSummary={(p) => publicBooking.summary(a.organization_slug, p)} onSelect={(slot) => reschedule.mutate({ appt: a, slot })} /> : null}
                </CardContent>
              </Card>
            ))}
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Past</h3>
            {past.length === 0 ? <p className="text-sm text-muted-foreground">No past appointments.</p> : past.map((a) => <Card key={a.id} className="py-4"><CardContent><AppointmentSummary appt={a} /></CardContent></Card>)}
          </section>
        </>
      )}
    </div>
  );
}
