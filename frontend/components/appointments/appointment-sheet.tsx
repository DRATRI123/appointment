"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/components/auth/auth-provider";
import { appointmentsService, schedulingService } from "@/services/booking";
import { paymentsService } from "@/services/payments";
import { PaymentStatusBadge } from "@/components/payments/payment-status-badge";
import { PaymentSheet } from "@/components/payments/payment-sheet";
import { formatPaise } from "@/lib/utils";
import { METHOD_LABEL } from "@/types/payment";
import { AppointmentSummary, StatusBadge } from "@/components/booking/appointment-summary";
import { SlotPicker } from "@/components/booking/slot-picker";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { AppointmentDetail } from "@/types/booking";

const ACTIONS: { action: string; label: string; from: string[]; perm: string; variant?: "default" | "outline" | "destructive" | "ghost" }[] = [
  { action: "confirm", label: "Confirm", from: ["pending_payment", "pending_verification", "draft"], perm: "appointments:write" },
  { action: "check_in", label: "Check in", from: ["confirmed", "pending_payment"], perm: "appointments:checkin" },
  { action: "start", label: "Start", from: ["checked_in", "confirmed"], perm: "appointments:checkin" },
  { action: "complete", label: "Complete", from: ["in_progress", "checked_in", "confirmed"], perm: "appointments:checkin" },
  { action: "no_show", label: "No show", from: ["confirmed", "pending_payment", "checked_in"], perm: "appointments:checkin", variant: "outline" },
  { action: "cancel", label: "Cancel", from: ["draft", "pending_payment", "pending_verification", "confirmed", "checked_in"], perm: "appointments:write", variant: "destructive" },
];

export function AppointmentSheet({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged?: () => void }) {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const appt = useQuery({ queryKey: ["appointment", id], queryFn: () => appointmentsService.get(id) });
  const [reason, setReason] = useState("");
  const [rescheduling, setRescheduling] = useState(false);
  const refresh = () => { queryClient.invalidateQueries({ queryKey: ["appointment", id] }); queryClient.invalidateQueries({ queryKey: ["appointments"] }); queryClient.invalidateQueries({ queryKey: ["calendar"] }); onChanged?.(); };
  const act = useMutation({
    mutationFn: (action: string) => appointmentsService.status(id, action, reason || undefined),
    onSuccess: (a) => { toast.success(`Appointment ${a.status.replace(/_/g, " ")}`); setReason(""); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reschedule = useMutation({
    mutationFn: (start_at: string) => appointmentsService.reschedule(id, { start_at, reason: reason || undefined }),
    onSuccess: () => { toast.success("Appointment moved"); setRescheduling(false); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const a: AppointmentDetail | undefined = appt.data;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">{a?.customer.full_name ?? "Appointment"} {a ? <span data-testid="appointment-status"><StatusBadge status={a.status} /></span> : null}</SheetTitle>
          <SheetDescription>{a ? `${a.service_name} with ${a.professional_name} · ${a.branch_name}` : ""}</SheetDescription>
        </SheetHeader>
        {!a ? <Skeleton className="h-48" /> : (
          <div className="space-y-6">
            <AppointmentSummary appt={a} showCustomer />
            {a.internal_notes ? <p className="rounded-lg bg-muted/50 p-3 text-sm"><span className="font-medium">Internal note:</span> {a.internal_notes}</p> : null}
            {a.form_answers && Object.keys(a.form_answers).length ? (
              <div className="rounded-lg border p-3 text-sm" data-testid="form-answers">
                <p className="mb-2 font-medium">Booking form answers</p>
                <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2">{Object.entries(a.form_answers).map(([k, v]) => <div key={k}><dt className="text-xs uppercase tracking-wide text-muted-foreground">{k.replace(/_/g, " ")}</dt><dd>{Array.isArray(v) ? v.map((x) => (typeof x === "object" && x && "name" in x ? (x as { name: string }).name : String(x))).join(", ") : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v)}</dd></div>)}</dl>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground"><Link href={`/admin/customers/${a.customer.id}`} className="underline">Open customer record</Link></p>
            <AppointmentPayments appointmentId={a.id} total={a.total_amount_paise} paid={a.paid_amount_paise} advanceDue={a.advance_due_paise} closed={["cancelled", "expired", "no_show"].includes(a.status)} />
            {a.status === "pending_payment" ? <p className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">Awaiting payment{a.payment_due_at ? ` until ${formatDateTime(a.payment_due_at)}` : ""}. Use <strong>Confirm</strong> only after payment is received; the UPI verification queue arrives in Phase 6.</p> : null}
            <div className="space-y-2">
              <Textarea placeholder="Reason / note for this action (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                {ACTIONS.filter((x) => x.from.includes(a.status) && hasPermission(x.perm)).map((x) => (
                  <Button key={x.action} size="sm" variant={x.variant ?? "default"} disabled={act.isPending} onClick={() => { if (x.action === "cancel" && !confirm("Cancel this appointment?")) return; act.mutate(x.action); }} data-testid={`action-${x.action}`}>{x.label}</Button>
                ))}
                {["pending_payment", "pending_verification", "confirmed"].includes(a.status) && hasPermission("appointments:write") ? (
                  <Button size="sm" variant="outline" onClick={() => setRescheduling((v) => !v)}>{rescheduling ? "Close reschedule" : "Reschedule"}</Button>
                ) : null}
              </div>
            </div>
            {rescheduling ? (
              <SlotPicker serviceId={a.service_id} branchId={a.branch_id} professionalId={a.professional_id} fetchDay={schedulingService.availability} fetchSummary={schedulingService.summary} onSelect={(s) => reschedule.mutate(s.start_at)} />
            ) : null}
            <div>
              <p className="mb-2 text-sm font-medium">History</p>
              <ol className="space-y-1 text-xs text-muted-foreground">
                {a.history.map((h, i) => <li key={i}>{formatDateTime(h.changed_at)} · {h.from_status ? `${h.from_status} → ` : ""}{h.to_status}{h.changed_by ? ` · ${h.changed_by}` : ""}{h.reason ? ` · ${h.reason}` : ""}</li>)}
              </ol>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}


function AppointmentPayments({ appointmentId, total, paid, advanceDue, closed }: { appointmentId: string; total: number; paid: number; advanceDue: number; closed: boolean }) {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const payments = useQuery({ queryKey: ["payments", "appointment", appointmentId], queryFn: () => paymentsService.list({ appointment_id: appointmentId, page_size: 50 }), enabled: hasPermission("payments:read") });
  const create = useMutation({
    mutationFn: (body: { kind: string; method: string }) => paymentsService.create({ appointment_id: appointmentId, ...body }),
    onSuccess: (p) => { toast.success(p.method === "cash" ? `Cash ${formatPaise(p.amount_paise)} recorded` : `UPI request for ${formatPaise(p.amount_paise)} created`); ["payments", "appointment", "appointments", "calendar"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })); if (p.method !== "cash") setOpen(p.id); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!hasPermission("payments:read")) return null;
  const balance = Math.max(0, total - paid);
  const advanceLeft = Math.max(0, advanceDue - paid);
  return (
    <div className="space-y-2 rounded-lg border p-3 text-sm" data-testid="appointment-payments">
      <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">Payments</p><span className="text-xs text-muted-foreground">Paid {formatPaise(paid)} of {formatPaise(total)}{balance ? ` · balance ${formatPaise(balance)}` : ""}</span></div>
      <ul className="divide-y">{payments.data?.data.map((p) => <li key={p.id} className="flex cursor-pointer items-center justify-between gap-2 py-1.5 hover:bg-muted/40" onClick={() => setOpen(p.id)}><span>{formatPaise(p.amount_paise)} · {METHOD_LABEL[p.method]} · {p.kind}{p.latest_utr ? <span className="ml-1 font-mono text-xs text-muted-foreground">{p.latest_utr}</span> : null}</span><PaymentStatusBadge status={p.status} /></li>)}{payments.data?.data.length === 0 ? <li className="py-2 text-muted-foreground">No payments yet.</li> : null}</ul>
      {!closed && hasPermission("payments:record") && balance > 0 ? (
        <div className="flex flex-wrap gap-2 pt-1">
          {advanceLeft > 0 ? <Button size="sm" variant="outline" onClick={() => create.mutate({ kind: "advance", method: "cash" })} disabled={create.isPending} data-testid="record-cash-advance">Cash advance {formatPaise(advanceLeft)}</Button> : null}
          <Button size="sm" variant="outline" onClick={() => create.mutate({ kind: "balance", method: "cash" })} disabled={create.isPending} data-testid="record-cash-balance">Cash balance {formatPaise(balance)}</Button>
          <Button size="sm" variant="outline" onClick={() => create.mutate({ kind: advanceLeft > 0 ? "advance" : "balance", method: "upi_qr" })} disabled={create.isPending}>UPI request {formatPaise(advanceLeft > 0 ? advanceLeft : balance)}</Button>
        </div>
      ) : null}
      {open ? <PaymentSheet id={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
