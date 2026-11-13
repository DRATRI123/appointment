"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, X } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { schedulingService } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { ScheduleWindow } from "@/types/booking";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const t = (v: string) => (v.length === 5 ? `${v}:00` : v);

export function SchedulesPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("professionals:schedule");
  const params = useSearchParams();
  const professionals = useQuery({ queryKey: ["professionals"], queryFn: () => catalogService.professionals(), enabled: !!orgId });
  const [chosenProfessional, setProfessionalId] = useState(params.get("professional") ?? "");
  const [chosenBranch, setBranchId] = useState("");
  const professionalId = chosenProfessional || professionals.data?.[0]?.id || "";
  const pro = professionals.data?.find((p) => p.id === professionalId) ?? null;
  const branchId = pro && pro.branches.some((b) => b.branch_id === chosenBranch) ? chosenBranch : (pro?.branches[0]?.branch_id ?? "");

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Schedules & availability" description="Weekly working hours per professional and branch, date exceptions, leave and organization holidays." />
      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <Field label="Professional" htmlFor="sc_pro"><NativeSelect id="sc_pro" value={professionalId} onChange={(e) => setProfessionalId(e.target.value)}>{professionals.data?.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}</NativeSelect></Field>
        <Field label="Branch" htmlFor="sc_branch"><NativeSelect id="sc_branch" value={branchId} onChange={(e) => setBranchId(e.target.value)}>{pro?.branches.map((b) => <option key={b.branch_id} value={b.branch_id}>{b.branch_name}</option>)}</NativeSelect></Field>
      </div>
      {!pro ? <Skeleton className="h-48" /> : pro.branches.length === 0 ? <p className="text-sm text-muted-foreground">Assign this professional to a branch first (Professionals → Edit → Branches &amp; fees).</p> : (
        <Tabs defaultValue="weekly">
          <TabsList className="mb-4"><TabsTrigger value="weekly">Weekly hours</TabsTrigger><TabsTrigger value="exceptions">Date exceptions</TabsTrigger><TabsTrigger value="leaves">Leave</TabsTrigger><TabsTrigger value="holidays">Holidays</TabsTrigger></TabsList>
          <TabsContent value="weekly">{branchId ? <WeeklyEditor key={`${professionalId}-${branchId}`} professionalId={professionalId} branchId={branchId} canWrite={canWrite} /> : null}</TabsContent>
          <TabsContent value="exceptions"><Exceptions professionalId={professionalId} canWrite={canWrite} /></TabsContent>
          <TabsContent value="leaves"><Leaves professionalId={professionalId} canWrite={canWrite} /></TabsContent>
          <TabsContent value="holidays"><Holidays canWrite={hasPermission("branches:write")} /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function WeeklyEditor({ professionalId, branchId, canWrite }: { professionalId: string; branchId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const schedules = useQuery({ queryKey: ["schedules", professionalId, branchId], queryFn: () => schedulingService.schedules({ professional_id: professionalId, branch_id: branchId }) });
  const [windows, setWindows] = useState<ScheduleWindow[] | null>(null);
  const current = windows ?? (schedules.data ?? []).map((s) => ({ weekday: s.weekday, start_time: s.start_time, end_time: s.end_time, slot_minutes: s.slot_minutes, capacity: s.capacity, consultation_mode: s.consultation_mode, valid_from: s.valid_from, valid_to: s.valid_to }));
  const save = useMutation({
    mutationFn: () => schedulingService.setSchedule(professionalId, branchId, current.map((w) => ({ ...w, start_time: t(w.start_time), end_time: t(w.end_time) }))),
    onSuccess: () => { toast.success("Weekly hours saved"); setWindows(null); queryClient.invalidateQueries({ queryKey: ["schedules", professionalId, branchId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const update = (next: ScheduleWindow[]) => setWindows(next);
  const copyMonToAll = () => { const mon = current.filter((w) => w.weekday === 0); update([0, 1, 2, 3, 4].flatMap((d) => mon.map((w) => ({ ...w, weekday: d })))); };
  if (schedules.isLoading) return <Skeleton className="h-64" />;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between">
        <div><CardTitle>Weekly hours</CardTitle><CardDescription>Add one or more windows per day (e.g. morning and evening). Slot length defaults to the professional&apos;s setting.</CardDescription></div>
        {canWrite ? <div className="flex gap-2"><Button size="sm" variant="outline" type="button" onClick={copyMonToAll}>Copy Monday to Mon–Fri</Button><Button size="sm" onClick={() => save.mutate()} disabled={save.isPending || windows === null} data-testid="save-schedule">Save</Button></div> : null}
      </CardHeader>
      <CardContent className="divide-y">
        {DAYS.map((label, day) => {
          const rows = current.map((w, i) => [w, i] as const).filter(([w]) => w.weekday === day);
          return (
            <div key={day} className="flex flex-wrap items-start gap-3 py-3">
              <div className="flex w-36 items-center gap-2 pt-1.5">
                <Switch checked={rows.length > 0} disabled={!canWrite} onCheckedChange={(v) => update(v ? [...current, { weekday: day, start_time: "09:00", end_time: "17:00", slot_minutes: null, capacity: 1, consultation_mode: null, valid_from: null, valid_to: null }] : current.filter((w) => w.weekday !== day))} aria-label={`${label} working`} />
                <span className="text-sm font-medium">{label}</span>
              </div>
              <div className="flex flex-1 flex-col gap-2">
                {rows.length === 0 ? <span className="pt-1.5 text-sm text-muted-foreground">Not working</span> : rows.map(([w, i]) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    <Input type="time" className="w-32" value={w.start_time.slice(0, 5)} disabled={!canWrite} onChange={(e) => update(current.map((x, j) => (j === i ? { ...x, start_time: e.target.value } : x)))} />
                    <span className="text-xs text-muted-foreground">to</span>
                    <Input type="time" className="w-32" value={w.end_time.slice(0, 5)} disabled={!canWrite} onChange={(e) => update(current.map((x, j) => (j === i ? { ...x, end_time: e.target.value } : x)))} />
                    <Input type="number" className="w-24" min={5} placeholder="slot min" value={w.slot_minutes ?? ""} disabled={!canWrite} onChange={(e) => update(current.map((x, j) => (j === i ? { ...x, slot_minutes: e.target.value ? Number(e.target.value) : null } : x)))} aria-label="Slot minutes" />
                    <Input type="number" className="w-20" min={1} value={w.capacity} disabled={!canWrite} onChange={(e) => update(current.map((x, j) => (j === i ? { ...x, capacity: Number(e.target.value) } : x)))} aria-label="Capacity" />
                    {canWrite ? <Button type="button" size="icon" variant="ghost" onClick={() => update(current.filter((_, j) => j !== i))} aria-label="Remove window"><X /></Button> : null}
                  </div>
                ))}
                {rows.length > 0 && canWrite ? <Button type="button" size="sm" variant="ghost" className="w-fit" onClick={() => update([...current, { weekday: day, start_time: "16:00", end_time: "20:00", slot_minutes: null, capacity: 1, consultation_mode: null, valid_from: null, valid_to: null }])}><Plus /> Add window</Button> : null}
              </div>
            </div>
          );
        })}
        <p className="pt-3 text-xs text-muted-foreground">Columns: start, end, slot minutes (blank = default), patients per slot.</p>
      </CardContent>
    </Card>
  );
}

function Exceptions({ professionalId, canWrite }: { professionalId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["exceptions", professionalId], queryFn: () => schedulingService.exceptions({ professional_id: professionalId }) });
  const [form, setForm] = useState({ date: "", is_available: false, start_time: "10:00", end_time: "13:00", reason: "" });
  const add = useMutation({
    mutationFn: () => schedulingService.addException({ professional_id: professionalId, date: form.date, is_available: form.is_available, start_time: form.is_available ? t(form.start_time) : null, end_time: form.is_available ? t(form.end_time) : null, reason: form.reason || null }),
    onSuccess: () => { toast.success("Exception added"); queryClient.invalidateQueries({ queryKey: ["exceptions", professionalId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({ mutationFn: (id: number) => schedulingService.deleteException(id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["exceptions", professionalId] }) });
  return (
    <Card>
      <CardHeader><CardTitle>Date exceptions</CardTitle><CardDescription>Block a specific day, or open extra hours on a day that is normally off.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? (
          <form className="grid items-end gap-3 sm:grid-cols-[150px_auto_1fr_auto]" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <Field label="Date" htmlFor="ex_date"><Input id="ex_date" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
            <label className="flex items-center gap-2 pb-2 text-sm"><Switch checked={form.is_available} onCheckedChange={(v) => setForm({ ...form, is_available: v })} /> {form.is_available ? "Extra hours" : "Day off"}</label>
            {form.is_available ? <div className="flex items-center gap-2"><Input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /><span className="text-xs">to</span><Input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} /></div> : <Input placeholder="Reason (optional)" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />}
            <Button type="submit" disabled={add.isPending}>Add</Button>
          </form>
        ) : null}
        <ul className="divide-y rounded-lg border">
          {list.data?.map((x) => <li key={x.id} className="flex items-center justify-between px-3 py-2 text-sm"><span>{x.date} · {x.is_available ? <Badge variant="success">open {x.start_time?.slice(0, 5)}–{x.end_time?.slice(0, 5)}</Badge> : <Badge variant="destructive">day off</Badge>} {x.reason ? <span className="text-muted-foreground">· {x.reason}</span> : null}</span>{canWrite ? <Button size="sm" variant="ghost" onClick={() => remove.mutate(x.id)}>Remove</Button> : null}</li>)}
          {list.data?.length === 0 ? <li className="px-3 py-6 text-center text-sm text-muted-foreground">No exceptions.</li> : null}
        </ul>
      </CardContent>
    </Card>
  );
}

function Leaves({ professionalId, canWrite }: { professionalId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["leaves", professionalId], queryFn: () => schedulingService.leaves({ professional_id: professionalId }) });
  const [form, setForm] = useState({ start: "", end: "", reason: "" });
  const add = useMutation({
    mutationFn: () => schedulingService.addLeave({ professional_id: professionalId, start_at: new Date(form.start).toISOString(), end_at: new Date(form.end).toISOString(), reason: form.reason || null }),
    onSuccess: () => { toast.success("Leave added"); queryClient.invalidateQueries({ queryKey: ["leaves", professionalId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({ mutationFn: (id: string) => schedulingService.deleteLeave(id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leaves", professionalId] }) });
  return (
    <Card>
      <CardHeader><CardTitle>Leave</CardTitle><CardDescription>Approved leave removes those hours from availability at every branch.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? (
          <form className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <Field label="From" htmlFor="lv_from"><Input id="lv_from" type="datetime-local" required value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
            <Field label="To" htmlFor="lv_to"><Input id="lv_to" type="datetime-local" required value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
            <Field label="Reason" htmlFor="lv_reason"><Input id="lv_reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
            <Button type="submit" disabled={add.isPending}>Add leave</Button>
          </form>
        ) : null}
        <ul className="divide-y rounded-lg border">
          {list.data?.map((l) => <li key={l.id} className="flex items-center justify-between px-3 py-2 text-sm"><span>{formatDateTime(l.start_at)} → {formatDateTime(l.end_at)} <Badge variant="secondary">{l.status}</Badge> {l.reason ? <span className="text-muted-foreground">· {l.reason}</span> : null}</span>{canWrite ? <Button size="sm" variant="ghost" onClick={() => remove.mutate(l.id)}>Remove</Button> : null}</li>)}
          {list.data?.length === 0 ? <li className="px-3 py-6 text-center text-sm text-muted-foreground">No leave recorded.</li> : null}
        </ul>
      </CardContent>
    </Card>
  );
}

function Holidays({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["holidays"], queryFn: schedulingService.holidays });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => catalogService.branches() });
  const [form, setForm] = useState({ date: "", name: "", branch_id: "", yearly: false });
  const add = useMutation({
    mutationFn: () => schedulingService.addHoliday({ date: form.date, name: form.name, branch_id: form.branch_id || null, is_recurring_yearly: form.yearly }),
    onSuccess: () => { toast.success("Holiday added"); queryClient.invalidateQueries({ queryKey: ["holidays"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({ mutationFn: (id: number) => schedulingService.deleteHoliday(id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["holidays"] }) });
  return (
    <Card>
      <CardHeader><CardTitle>Holidays</CardTitle><CardDescription>Organization-wide or per branch. Yearly holidays repeat on the same date.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? (
          <form className="grid items-end gap-3 sm:grid-cols-[150px_1fr_1fr_auto_auto]" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <Field label="Date" htmlFor="h_date"><Input id="h_date" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
            <Field label="Name" htmlFor="h_name"><Input id="h_name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Branch" htmlFor="h_branch"><NativeSelect id="h_branch" value={form.branch_id} onChange={(e) => setForm({ ...form, branch_id: e.target.value })}><option value="">All branches</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</NativeSelect></Field>
            <label className="flex items-center gap-2 pb-2 text-sm"><Switch checked={form.yearly} onCheckedChange={(v) => setForm({ ...form, yearly: v })} /> Yearly</label>
            <Button type="submit" disabled={add.isPending}>Add</Button>
          </form>
        ) : null}
        <ul className="divide-y rounded-lg border">
          {list.data?.map((h) => <li key={h.id} className="flex items-center justify-between px-3 py-2 text-sm"><span>{h.date} · {h.name} {h.is_recurring_yearly ? <Badge variant="secondary">yearly</Badge> : null} {h.branch_id ? <Badge variant="outline">{branches.data?.find((b) => b.id === h.branch_id)?.name}</Badge> : <Badge variant="outline">all branches</Badge>}</span>{canWrite ? <Button size="sm" variant="ghost" onClick={() => remove.mutate(h.id)}>Remove</Button> : null}</li>)}
          {list.data?.length === 0 ? <li className="px-3 py-6 text-center text-sm text-muted-foreground">No holidays.</li> : null}
        </ul>
      </CardContent>
    </Card>
  );
}
