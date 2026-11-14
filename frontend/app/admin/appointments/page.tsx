"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { appointmentsService } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/booking/appointment-summary";
import { AppointmentSheet } from "@/components/appointments/appointment-sheet";
import { NewAppointmentSheet } from "@/components/appointments/new-appointment-sheet";
import { addDays, formatDateLong, formatTime, toISODate } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { STATUS_LABEL } from "@/types/booking";

export default function AppointmentsPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const [from, setFrom] = useState(toISODate(new Date()));
  const [to, setTo] = useState(toISODate(addDays(new Date(), 7)));
  const [status, setStatus] = useState("");
  const [professionalId, setProfessionalId] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const professionals = useQuery({ queryKey: ["professionals"], queryFn: () => catalogService.professionals(), enabled: !!orgId });
  const appts = useQuery({
    queryKey: ["appointments", orgId, from, to, status, professionalId, search],
    queryFn: () => appointmentsService.list({ from_at: new Date(`${from}T00:00:00`).toISOString(), to_at: new Date(`${to}T23:59:59`).toISOString(), status: status || undefined, professional_id: professionalId || undefined, search: search || undefined }),
    enabled: !!orgId,
  });
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Appointments" description="Search, filter and act on bookings. Pending payments expire automatically after the payment window." actions={hasPermission("appointments:write") ? <Button onClick={() => setCreating(true)}><Plus /> New appointment</Button> : null} />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From date" />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date" />
        <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect>
        <NativeSelect aria-label="Professional" value={professionalId} onChange={(e) => setProfessionalId(e.target.value)}><option value="">All professionals</option>{professionals.data?.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}</NativeSelect>
        <Input placeholder="Search name, mobile, reference" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {appts.isLoading ? <Skeleton className="h-64" /> : appts.data?.length === 0 ? (
        <EmptyState icon={CalendarDays} title="No appointments in this range" body="Widen the date range or create a booking for a walk-in customer." />
      ) : (
        <Table>
          <TableHeader><TableRow><TableHead>When</TableHead><TableHead>Customer</TableHead><TableHead>Service</TableHead><TableHead>Professional</TableHead><TableHead>Amount</TableHead><TableHead>Status</TableHead><TableHead>Ref</TableHead></TableRow></TableHeader>
          <TableBody>
            {appts.data?.map((a) => (
              <TableRow key={a.id} className="cursor-pointer" onClick={() => setSelected(a.id)} data-testid="appointment-row">
                <TableCell className="whitespace-nowrap"><span className="font-medium">{formatTime(a.start_at, a.timezone)}</span><span className="block text-xs text-muted-foreground">{formatDateLong(a.start_at, a.timezone)}</span></TableCell>
                <TableCell>{a.customer.full_name}<span className="block text-xs text-muted-foreground">{a.customer.mobile ?? a.customer.email}</span></TableCell>
                <TableCell>{a.service_name}</TableCell>
                <TableCell>{a.professional_name}<span className="block text-xs text-muted-foreground">{a.branch_name}</span></TableCell>
                <TableCell>{formatPaise(a.total_amount_paise)}{a.advance_due_paise > a.paid_amount_paise ? <span className="block text-xs text-warning-foreground text-muted-foreground">due {formatPaise(a.advance_due_paise - a.paid_amount_paise)}</span> : null}</TableCell>
                <TableCell><StatusBadge status={a.status} /></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{a.reference.split("-").pop()?.slice(-6)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {selected ? <AppointmentSheet id={selected} onClose={() => setSelected(null)} /> : null}
      {creating ? <NewAppointmentSheet onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setSelected(id); appts.refetch(); }} /> : null}
    </div>
  );
}
