"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { appointmentsService } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/booking/appointment-summary";
import { AppointmentSheet } from "@/components/appointments/appointment-sheet";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { formatTime, toISODate } from "@/lib/format";
import { analyticsService } from "@/services/analytics";
import { presetRange } from "@/components/analytics/filters-bar";
import { StatTile } from "@/components/analytics/stat-tile";
import { compactNumber, percent } from "@/lib/numbers";

export default function ProfessionalToday() {
  const { currentOrganizationId: orgId, user } = useAuth();
  const [selected, setSelected] = useState<string | null>(null);
  const today = toISODate(new Date());
  const appts = useQuery({
    queryKey: ["appointments", "today", orgId],
    queryFn: () => appointmentsService.list({ from_at: new Date(`${today}T00:00:00`).toISOString(), to_at: new Date(`${today}T23:59:59`).toISOString() }),
    enabled: !!orgId,
    retry: false,
    refetchInterval: 60_000,
  });
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title={`Today, ${new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}`} description={`Your queue, ${user?.full_name ?? ""}. Tap a patient to check in, start or complete.`} />
      <MyMonth orgId={orgId} />
      {appts.isError ? <Alert variant="info"><AlertDescription>Your account is not linked to a professional profile yet. Ask an administrator to link it under Professionals → Account.</AlertDescription></Alert> : null}
      {appts.isLoading ? <Skeleton className="h-48" /> : appts.data?.length === 0 ? <EmptyState icon={CalendarDays} title="No appointments today" body="Enjoy the quiet, or check the calendar for the week ahead." /> : (
        <div className="space-y-2">
          {appts.data?.map((a) => (
            <Card key={a.id} className="cursor-pointer py-3 transition-shadow hover:shadow-md" onClick={() => setSelected(a.id)}>
              <CardContent className="flex items-center gap-4">
                <div className="w-20 text-center"><p className="text-lg font-semibold">{formatTime(a.start_at, a.timezone)}</p><p className="text-xs text-muted-foreground">{formatTime(a.end_at, a.timezone)}</p></div>
                <div className="min-w-0 flex-1"><p className="truncate font-medium">{a.customer.full_name}</p><p className="truncate text-sm text-muted-foreground">{a.service_name} · {a.branch_name}{a.customer_notes ? ` · “${a.customer_notes}”` : ""}</p></div>
                <StatusBadge status={a.status} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {selected ? <AppointmentSheet id={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}

function MyMonth({ orgId }: { orgId: string | null }) {
  const timeZone = useAuth().currentMembership?.organization?.timezone;
  const stats = useQuery({ queryKey: ["dashboard", "mine", orgId], queryFn: () => analyticsService.dashboard(presetRange("30d", new Date(), timeZone), true), enabled: !!orgId, retry: false });
  const k = stats.data?.kpis;
  if (!k || stats.data?.scope !== "professional") return null;
  const pro = stats.data.by_professional[0];
  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-3" data-testid="my-stats">
      <StatTile label="Appointments, last 30 days" value={compactNumber(k.appointments.value)} current={k.appointments.value} previous={k.appointments.previous} comparison="previous 30 days" />
      <StatTile label="No-show rate" value={percent(k.no_show_rate.value)} current={k.no_show_rate.value} previous={k.no_show_rate.previous} upIsGood={false} format={(n) => percent(n)} comparison="previous 30 days" />
      <StatTile label="Schedule booked" value={percent(pro?.utilization ?? null)} hint={pro?.available_minutes ? `${(pro.booked_minutes / 60).toFixed(1)} of ${(pro.available_minutes / 60).toFixed(1)} scheduled hours` : "No schedule in this period"} />
    </div>
  );
}

