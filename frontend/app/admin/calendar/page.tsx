"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import dayGridPlugin from "@fullcalendar/react/daygrid";
import timeGridPlugin from "@fullcalendar/react/timegrid";
import interactionPlugin from "@fullcalendar/react/interaction";
import breezyTheme from "@fullcalendar/react/themes/breezy";
import "@fullcalendar/react/skeleton.css";
import "@fullcalendar/react/themes/breezy/theme.css";
import "@fullcalendar/react/themes/breezy/palettes/emerald.css";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { appointmentsService } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { AppointmentSheet } from "@/components/appointments/appointment-sheet";
import { NewAppointmentSheet } from "@/components/appointments/new-appointment-sheet";
import type { CalendarEvent } from "@/types/booking";

const FullCalendar = dynamic(() => import("@fullcalendar/react"), { ssr: false });

const COLORS: Record<string, string> = {
  pending_payment: "#d97706", pending_verification: "#d97706", confirmed: "#0f766e", checked_in: "#2563eb", in_progress: "#7c3aed",
  completed: "#64748b", cancelled: "#dc2626", no_show: "#b91c1c", expired: "#9ca3af", draft: "#9ca3af", rescheduled: "#0ea5e9",
};

export default function CalendarPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const [range, setRange] = useState<{ from: string; to: string } | null>(null);
  const [professionalId, setProfessionalId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState<{ start?: Date } | null>(null);
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => catalogService.branches(), enabled: !!orgId });
  const professionals = useQuery({ queryKey: ["professionals"], queryFn: () => catalogService.professionals(), enabled: !!orgId });
  const events = useQuery({
    queryKey: ["calendar", orgId, range, professionalId, branchId],
    queryFn: () => appointmentsService.calendar({ from_at: range!.from, to_at: range!.to, professional_id: professionalId || undefined, branch_id: branchId || undefined }),
    enabled: !!orgId && !!range,
    refetchInterval: 60_000,
  });
  const fcEvents = useMemo(() => (events.data ?? []).map((e: CalendarEvent) => ({ id: e.id, title: e.title, start: e.start, end: e.end, backgroundColor: COLORS[e.status], borderColor: COLORS[e.status], extendedProps: e })), [events.data]);

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Calendar" description="Day, week and month views across professionals and branches. Click an appointment for details and actions." actions={
        <div className="flex flex-wrap gap-2">
          <NativeSelect aria-label="Branch" className="w-44" value={branchId} onChange={(e) => setBranchId(e.target.value)}><option value="">All branches</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</NativeSelect>
          <NativeSelect aria-label="Professional" className="w-52" value={professionalId} onChange={(e) => setProfessionalId(e.target.value)}><option value="">All professionals</option>{professionals.data?.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}</NativeSelect>
          {hasPermission("appointments:write") ? <Button onClick={() => setCreating({})}><Plus /> New appointment</Button> : null}
        </div>
      } />
      <div className="app-calendar rounded-xl border bg-card p-3 text-sm" data-testid="calendar">
        <FullCalendar
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin, breezyTheme]}
          initialView="timeGridWeek"
          headerToolbar={{ left: "prev,next today", center: "title", right: "timeGridDay,timeGridWeek,dayGridMonth" }}
          todayText="Today"
          todayHint="Today"
          viewHint={(text: string) => `${text} view`}
          slotMinTime="07:00:00"
          slotMaxTime="22:00:00"
          allDaySlot={false}
          nowIndicator
          height="auto"
          events={fcEvents}
          datesSet={(arg) => setRange({ from: arg.start.toISOString(), to: arg.end.toISOString() })}
          eventClick={(arg) => setSelected(arg.event.id)}
          dateClick={(arg) => { if (hasPermission("appointments:write")) setCreating({ start: arg.date }); }}
          eventContent={(arg) => <div className="truncate text-xs leading-tight"><b>{arg.timeText}</b> {arg.event.extendedProps.customer_name}<br /><span className="opacity-80">{arg.event.extendedProps.service_name}</span></div>}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">{Object.entries(COLORS).filter(([k]) => !["draft", "rescheduled"].includes(k)).map(([k, c]) => <span key={k} className="flex items-center gap-1"><span className="size-2.5 rounded-full" style={{ background: c }} />{k.replace(/_/g, " ")}</span>)}</div>
      {selected ? <AppointmentSheet id={selected} onClose={() => setSelected(null)} /> : null}
      {creating ? <NewAppointmentSheet defaults={{ start: creating.start, professional_id: professionalId || undefined, branch_id: branchId || undefined }} onClose={() => setCreating(null)} onCreated={(id) => { setCreating(null); setSelected(id); events.refetch(); }} /> : null}
    </div>
  );
}
