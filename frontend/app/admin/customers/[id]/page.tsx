"use client";

import { use, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, FileText, Lock, Paperclip, Users } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { customersService } from "@/services/customers";
import { appointmentsService } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/booking/appointment-summary";
import { AppointmentSheet } from "@/components/appointments/appointment-sheet";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { EraseCustomerDialog } from "@/components/customers/erase-dialog";
import { errorMessage } from "@/lib/errors";
import { formatDate, formatDateTime, formatTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import type { Customer } from "@/types/customer";

export default function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const customer = useQuery({ queryKey: ["customer", id], queryFn: () => customersService.get(id) });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["customer", id] });
  if (customer.isLoading) return <Skeleton className="h-64" />;
  if (!customer.data) return <p>Customer not found.</p>;
  const c = customer.data;
  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/admin/customers" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Customers</Link>
      <PageHeader title={c.full_name} description={[c.customer_code, c.mobile, c.email].filter(Boolean).join(" · ")} actions={<div className="flex flex-wrap items-center gap-2">{c.is_guest ? <Badge variant="outline">guest</Badge> : <Badge variant="success">registered</Badge>}{c.tags.map((t) => <Badge key={t} variant="secondary">{t}</Badge>)}{hasPermission("customers:erase") ? <EraseCustomerDialog customerId={c.id} name={c.full_name} /> : null}</div>} />
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        <Stat label="Appointments" value={c.stats?.total_appointments ?? 0} />
        <Stat label="Upcoming" value={c.stats?.upcoming_appointments ?? 0} />
        <Stat label="No-shows" value={c.stats?.no_shows ?? 0} />
        <Stat label="Paid" value={formatPaise(c.stats?.total_paid_paise ?? 0)} />
      </div>
      <Tabs defaultValue="appointments">
        <TabsList className="mb-4 flex h-auto flex-wrap"><TabsTrigger value="appointments">Appointments</TabsTrigger><TabsTrigger value="profile">Profile</TabsTrigger><TabsTrigger value="family">Family</TabsTrigger>{hasPermission("customers:clinical_read") ? <><TabsTrigger value="notes">Notes</TabsTrigger><TabsTrigger value="documents">Documents</TabsTrigger></> : null}</TabsList>
        <TabsContent value="appointments"><Appointments customerId={c.id} /></TabsContent>
        <TabsContent value="profile"><Profile customer={c} canWrite={hasPermission("customers:write")} onSaved={invalidate} /></TabsContent>
        <TabsContent value="family"><Family customerId={c.id} canWrite={hasPermission("customers:write")} /></TabsContent>
        <TabsContent value="notes"><Notes customerId={c.id} canWrite={hasPermission("customers:clinical_write")} /></TabsContent>
        <TabsContent value="documents"><Documents customerId={c.id} canWrite={hasPermission("customers:clinical_write")} /></TabsContent>
      </Tabs>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <Card className="gap-1 py-4"><CardHeader><CardDescription>{label}</CardDescription></CardHeader><CardContent className="text-xl font-semibold">{value}</CardContent></Card>;
}

function Appointments({ customerId }: { customerId: string }) {
  const appts = useQuery({ queryKey: ["appointments", "customer", customerId], queryFn: () => appointmentsService.list({ customer_id: customerId }) });
  const [selected, setSelected] = useState<string | null>(null);
  if (appts.isLoading) return <Skeleton className="h-40" />;
  const rows = [...(appts.data ?? [])].sort((a, b) => b.start_at.localeCompare(a.start_at));
  return (
    <Card>
      <CardHeader><CardTitle>History</CardTitle></CardHeader>
      <CardContent>
        {rows.length === 0 ? <p className="text-sm text-muted-foreground">No appointments yet.</p> : (
          <ul className="divide-y">{rows.map((a) => <li key={a.id} className="flex cursor-pointer items-center justify-between gap-3 py-2 text-sm hover:bg-muted/40" onClick={() => setSelected(a.id)}><span><span className="font-medium">{formatDate(a.start_at, a.timezone)} · {formatTime(a.start_at, a.timezone)}</span><span className="block text-xs text-muted-foreground">{a.service_name} · {a.professional_name} · {a.branch_name}{a.dependent_id ? " · family member" : ""}</span></span><StatusBadge status={a.status} /></li>)}</ul>
        )}
      </CardContent>
      {selected ? <AppointmentSheet id={selected} onClose={() => setSelected(null)} /> : null}
    </Card>
  );
}

function Profile({ customer, canWrite, onSaved }: { customer: Customer; canWrite: boolean; onSaved: () => void }) {
  const a = (customer.address ?? {}) as Record<string, string>;
  const [form, setForm] = useState({ full_name: customer.full_name, mobile: customer.mobile ?? "", email: customer.email ?? "", gender: customer.gender ?? "", date_of_birth: customer.date_of_birth ?? "", blood_group: customer.blood_group ?? "", tags: customer.tags.join(", "), line1: a.line1 ?? "", city: a.city ?? "", pincode: a.pincode ?? "", sms: customer.communication_preferences?.sms ?? true, whatsapp: customer.communication_preferences?.whatsapp ?? true, email_pref: customer.communication_preferences?.email ?? true, consent_data: customer.consent?.data_processing ?? false, consent_marketing: customer.consent?.marketing ?? false });
  const save = useMutation({
    mutationFn: () => customersService.update(customer.id, {
      full_name: form.full_name, mobile: form.mobile || null, email: form.email || null, gender: form.gender || null, date_of_birth: form.date_of_birth || null, blood_group: form.blood_group || null,
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean), address: { line1: form.line1, city: form.city, pincode: form.pincode },
      communication_preferences: { sms: form.sms, whatsapp: form.whatsapp, email: form.email_pref }, consent: { data_processing: form.consent_data, marketing: form.consent_marketing },
    }),
    onSuccess: () => { toast.success("Profile saved"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Card>
      <CardHeader><CardTitle>Profile</CardTitle><CardDescription>Contact details, communication preferences and consent.</CardDescription></CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="customer-profile-form">
          <Field label="Full name" htmlFor="cp_name"><Input id="cp_name" value={form.full_name} onChange={set("full_name")} disabled={!canWrite} /></Field>
          <Field label="Tags" htmlFor="cp_tags"><Input id="cp_tags" value={form.tags} onChange={set("tags")} disabled={!canWrite} /></Field>
          <Field label="Mobile" htmlFor="cp_mobile"><Input id="cp_mobile" value={form.mobile} onChange={set("mobile")} disabled={!canWrite} /></Field>
          <Field label="Email" htmlFor="cp_email"><Input id="cp_email" type="email" value={form.email} onChange={set("email")} disabled={!canWrite} /></Field>
          <Field label="Gender" htmlFor="cp_gender"><NativeSelect id="cp_gender" value={form.gender} onChange={set("gender")} disabled={!canWrite}><option value="">—</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="undisclosed">Prefer not to say</option></NativeSelect></Field>
          <Field label="Date of birth" htmlFor="cp_dob"><Input id="cp_dob" type="date" value={form.date_of_birth} onChange={set("date_of_birth")} disabled={!canWrite} /></Field>
          <Field label="Blood group" htmlFor="cp_blood"><Input id="cp_blood" value={form.blood_group} onChange={set("blood_group")} disabled={!canWrite} /></Field>
          <Field label="Address" htmlFor="cp_line1"><Input id="cp_line1" placeholder="Street" value={form.line1} onChange={set("line1")} disabled={!canWrite} /></Field>
          <Field label="City" htmlFor="cp_city"><Input id="cp_city" value={form.city} onChange={set("city")} disabled={!canWrite} /></Field>
          <Field label="PIN code" htmlFor="cp_pin"><Input id="cp_pin" value={form.pincode} onChange={set("pincode")} disabled={!canWrite} /></Field>
          <div className="space-y-2 sm:col-span-2">
            <p className="text-sm font-medium">Communication preferences</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {([["sms", "SMS"], ["whatsapp", "WhatsApp"], ["email_pref", "Email"]] as const).map(([k, l]) => <label key={k} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>{l}</span><Switch checked={form[k] as boolean} disabled={!canWrite} onCheckedChange={(v) => setForm({ ...form, [k]: v })} /></label>)}
            </div>
          </div>
          <div className="space-y-2 sm:col-span-2">
            <p className="text-sm font-medium">Consent</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Data processing for appointments</span><Switch checked={form.consent_data} disabled={!canWrite} onCheckedChange={(v) => setForm({ ...form, consent_data: v })} /></label>
              <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Marketing messages</span><Switch checked={form.consent_marketing} disabled={!canWrite} onCheckedChange={(v) => setForm({ ...form, consent_marketing: v })} /></label>
            </div>
          </div>
          {canWrite ? <div className="flex justify-end sm:col-span-2"><Button type="submit" disabled={save.isPending}>Save</Button></div> : null}
        </form>
      </CardContent>
    </Card>
  );
}

function Family({ customerId, canWrite }: { customerId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const deps = useQuery({ queryKey: ["dependents", customerId], queryFn: () => customersService.dependents(customerId) });
  const [form, setForm] = useState({ full_name: "", relationship_label: "child", date_of_birth: "" });
  const add = useMutation({ mutationFn: () => customersService.addDependent(customerId, { ...form, date_of_birth: form.date_of_birth || null }), onSuccess: () => { toast.success("Family member added"); setForm({ full_name: "", relationship_label: "child", date_of_birth: "" }); queryClient.invalidateQueries({ queryKey: ["dependents", customerId] }); queryClient.invalidateQueries({ queryKey: ["customer", customerId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: (id: string) => customersService.removeDependent(customerId, id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dependents", customerId] }) });
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Users className="size-4" /> Family members</CardTitle><CardDescription>Dependents the customer can book appointments for.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? <form className="grid items-end gap-3 sm:grid-cols-[1fr_160px_160px_auto]" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}><Field label="Name" htmlFor="dp_name"><Input id="dp_name" required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field><Field label="Relationship" htmlFor="dp_rel"><NativeSelect id="dp_rel" value={form.relationship_label} onChange={(e) => setForm({ ...form, relationship_label: e.target.value })}>{["child", "spouse", "parent", "sibling", "other"].map((r) => <option key={r} value={r}>{r}</option>)}</NativeSelect></Field><Field label="Date of birth" htmlFor="dp_dob"><Input id="dp_dob" type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} /></Field><Button type="submit" disabled={add.isPending}>Add</Button></form> : null}
        <ul className="divide-y rounded-lg border">{deps.data?.map((d) => <li key={d.id} className="flex items-center justify-between px-3 py-2 text-sm"><span><span className="font-medium">{d.full_name}</span> <span className="text-muted-foreground">· {d.relationship_label}{d.date_of_birth ? ` · born ${formatDate(d.date_of_birth)}` : ""}</span></span>{canWrite ? <Button size="sm" variant="ghost" onClick={() => remove.mutate(d.id)}>Remove</Button> : null}</li>)}{deps.data?.length === 0 ? <li className="px-3 py-6 text-center text-sm text-muted-foreground">No family members.</li> : null}</ul>
      </CardContent>
    </Card>
  );
}

function Notes({ customerId, canWrite }: { customerId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [purpose] = useState("consultation");
  const notes = useQuery({ queryKey: ["notes", customerId], queryFn: () => customersService.notes(customerId, purpose) });
  const [form, setForm] = useState({ body: "", note_type: "clinical" });
  const add = useMutation({ mutationFn: () => customersService.addNote(customerId, form), onSuccess: () => { toast.success("Note saved"); setForm({ body: "", note_type: "clinical" }); queryClient.invalidateQueries({ queryKey: ["notes", customerId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: (id: string) => customersService.removeNote(customerId, id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notes", customerId] }) });
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Lock className="size-4" /> Clinical notes</CardTitle><CardDescription>Encrypted at rest. Every view is written to the audit log.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }} data-testid="note-form"><div className="flex gap-2"><NativeSelect className="w-44" value={form.note_type} onChange={(e) => setForm({ ...form, note_type: e.target.value })}>{["clinical", "allergy", "medication", "follow_up", "general", "admin"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</NativeSelect></div><Textarea required placeholder="Write a note…" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /><div className="flex justify-end"><Button type="submit" size="sm" disabled={add.isPending}>Add note</Button></div></form> : null}
        {notes.isLoading ? <Skeleton className="h-24" /> : <ul className="space-y-2">{notes.data?.map((n) => <li key={n.id} className="rounded-lg border p-3 text-sm" data-testid="note"><div className="mb-1 flex items-center justify-between gap-2"><span className="flex items-center gap-2"><Badge variant="secondary">{n.note_type.replace("_", " ")}</Badge><span className="text-xs text-muted-foreground">{n.author_name ?? "—"} · {formatDateTime(n.created_at)}</span></span>{canWrite ? <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm("Delete this note?")) remove.mutate(n.id); }}>Delete</Button> : null}</div><p className="whitespace-pre-line">{n.body}</p></li>)}{notes.data?.length === 0 ? <li className="py-6 text-center text-sm text-muted-foreground">No notes yet.</li> : null}</ul>}
      </CardContent>
    </Card>
  );
}

function Documents({ customerId, canWrite }: { customerId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const docs = useQuery({ queryKey: ["documents", customerId], queryFn: () => customersService.documents(customerId) });
  const input = useRef<HTMLInputElement>(null);
  const [meta, setMeta] = useState({ title: "", document_type: "report" });
  const upload = useMutation({ mutationFn: (file: File) => customersService.uploadDocument(customerId, file, meta.title || file.name, meta.document_type), onSuccess: () => { toast.success("Document uploaded"); setMeta({ title: "", document_type: "report" }); queryClient.invalidateQueries({ queryKey: ["documents", customerId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: (id: string) => customersService.removeDocument(customerId, id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", customerId] }) });
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Paperclip className="size-4" /> Documents</CardTitle><CardDescription>Reports, prescriptions and scans in private storage. Downloads are audit-logged and respect the retention policy.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? <div className="grid items-end gap-3 sm:grid-cols-[1fr_160px_auto]"><Field label="Title" htmlFor="doc_title"><Input id="doc_title" placeholder="Defaults to file name" value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></Field><Field label="Type" htmlFor="doc_type"><NativeSelect id="doc_type" value={meta.document_type} onChange={(e) => setMeta({ ...meta, document_type: e.target.value })}>{["report", "prescription", "scan", "id_proof", "consent", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</NativeSelect></Field><Button type="button" variant="outline" disabled={upload.isPending} onClick={() => input.current?.click()}><FileText /> Upload PDF or image</Button><input ref={input} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload.mutate(f); }} /></div> : null}
        <Alert variant="info"><AlertDescription>Files never pass through the public media folder. Staff with clinical access download them through an authenticated link.</AlertDescription></Alert>
        <ul className="divide-y rounded-lg border">{docs.data?.map((d) => <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"><span><a className="font-medium hover:underline" href={customersService.documentUrl(customerId, d.id)} target="_blank" rel="noreferrer">{d.title}</a><span className="block text-xs text-muted-foreground">{d.document_type.replace("_", " ")} · {(d.size_bytes / 1024).toFixed(0)} KB · {d.uploaded_by_name ?? "—"} · {formatDateTime(d.created_at)}{d.retention_until ? ` · kept until ${formatDate(d.retention_until)}` : ""}</span></span>{canWrite ? <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm("Delete this document?")) remove.mutate(d.id); }}>Delete</Button> : null}</li>)}{docs.data?.length === 0 ? <li className="px-3 py-6 text-center text-sm text-muted-foreground">No documents.</li> : null}</ul>
      </CardContent>
    </Card>
  );
}
