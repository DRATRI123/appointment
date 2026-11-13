"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { catalogService } from "@/services/catalog";
import { appointmentsService, schedulingService } from "@/services/booking";
import { SlotPicker } from "@/components/booking/slot-picker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateLong, formatTime } from "@/lib/format";
import type { Slot } from "@/types/booking";

export function NewAppointmentSheet({ onClose, onCreated, defaults }: { onClose: () => void; onCreated: (id: string) => void; defaults?: { professional_id?: string; branch_id?: string; start?: Date } }) {
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => catalogService.branches(false) });
  const services = useQuery({ queryKey: ["services-all"], queryFn: () => catalogService.services() });
  const [form, setForm] = useState({
    branch_id: defaults?.branch_id ?? "", service_id: "", professional_id: defaults?.professional_id ?? "", full_name: "", mobile: "", email: "",
    source: "reception", internal_notes: "", confirm_without_payment: false, recurring: false, occurrences: 4, interval_days: 7,
  });
  const professionals = useQuery({ queryKey: ["pros-for", form.branch_id, form.service_id], queryFn: () => catalogService.professionals({ branch_id: form.branch_id, service_id: form.service_id }), enabled: !!form.branch_id && !!form.service_id });
  const [slot, setSlot] = useState<Slot | null>(null);
  const [tz, setTz] = useState("Asia/Kolkata");
  const branchId = form.branch_id || branches.data?.find((b) => b.is_default)?.id || branches.data?.[0]?.id || "";

  const create = useMutation({
    mutationFn: () => {
      const body = {
        professional_id: slot!.professional_id, branch_id: branchId, service_id: form.service_id, start_at: slot!.start_at,
        customer: { full_name: form.full_name, mobile: form.mobile || undefined, email: form.email || undefined },
        source: form.source, internal_notes: form.internal_notes || undefined, confirm_without_payment: form.confirm_without_payment,
      };
      return form.recurring ? appointmentsService.createRecurring({ ...body, occurrences: form.occurrences, interval_days: form.interval_days }).then((r) => {
        if (r.skipped.length) toast.warning(`${r.skipped.length} occurrence(s) skipped: ${r.skipped.map((s) => s.reason).join("; ")}`);
        return r.created[0];
      }) : appointmentsService.create(body);
    },
    onSuccess: (a) => { toast.success(`Booked ${a.reference}`); onCreated(a.id); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-2xl">
        <SheetHeader><SheetTitle>New appointment</SheetTitle><SheetDescription>Reception or walk-in booking. Prices are computed by the server; staff can confirm without advance payment.</SheetDescription></SheetHeader>
        <form id="new-appt" className="space-y-5" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} data-testid="new-appointment-form">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Branch" htmlFor="na_branch"><NativeSelect id="na_branch" value={branchId} onChange={(e) => { setForm({ ...form, branch_id: e.target.value }); setSlot(null); }}>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</NativeSelect></Field>
            <Field label="Service" htmlFor="na_service"><NativeSelect id="na_service" required value={form.service_id} onChange={(e) => { setForm({ ...form, service_id: e.target.value }); setSlot(null); }}><option value="">Select…</option>{services.data?.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.duration_minutes} min</option>)}</NativeSelect></Field>
            <Field label="Professional" htmlFor="na_pro" className="sm:col-span-2"><NativeSelect id="na_pro" value={form.professional_id} onChange={(e) => { setForm({ ...form, professional_id: e.target.value }); setSlot(null); }}><option value="">Any available</option>{professionals.data?.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}</NativeSelect></Field>
          </div>
          {form.service_id && branchId ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">Date &amp; time {slot ? <span className="font-normal text-muted-foreground">· {formatDateLong(slot.start_at, tz)} {formatTime(slot.start_at, tz)}</span> : null}</p>
              <SlotPicker serviceId={form.service_id} branchId={branchId} professionalId={form.professional_id || undefined} fetchDay={schedulingService.availability} fetchSummary={schedulingService.summary} selected={slot} startDate={defaults?.start} onSelect={(s, day) => { setSlot(s); setTz(day.timezone); }} />
            </div>
          ) : <p className="text-sm text-muted-foreground">Choose a service to see available times.</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Customer name" htmlFor="na_name" className="sm:col-span-2"><Input id="na_name" required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            <Field label="Mobile" htmlFor="na_mobile"><Input id="na_mobile" inputMode="tel" required={!form.email} value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></Field>
            <Field label="Email" htmlFor="na_email"><Input id="na_email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Source" htmlFor="na_source"><NativeSelect id="na_source" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}><option value="reception">Reception (phone)</option><option value="walk_in">Walk-in</option><option value="professional">Professional</option></NativeSelect></Field>
            <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Confirm without payment</span><Switch checked={form.confirm_without_payment} onCheckedChange={(v) => setForm({ ...form, confirm_without_payment: v })} /></label>
            <Field label="Internal note" htmlFor="na_note" className="sm:col-span-2"><Textarea id="na_note" value={form.internal_notes} onChange={(e) => setForm({ ...form, internal_notes: e.target.value })} /></Field>
            <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm sm:col-span-2"><span>Repeat weekly (recurring series)</span><Switch checked={form.recurring} onCheckedChange={(v) => setForm({ ...form, recurring: v })} /></label>
            {form.recurring ? (<>
              <Field label="Occurrences" htmlFor="na_occ"><Input id="na_occ" type="number" min={2} max={26} value={form.occurrences} onChange={(e) => setForm({ ...form, occurrences: Number(e.target.value) })} /></Field>
              <Field label="Every N days" htmlFor="na_int"><Input id="na_int" type="number" min={1} max={90} value={form.interval_days} onChange={(e) => setForm({ ...form, interval_days: Number(e.target.value) })} /></Field>
            </>) : null}
          </div>
        </form>
        <SheetFooter><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" form="new-appt" disabled={!slot || create.isPending}>Book appointment</Button></SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
