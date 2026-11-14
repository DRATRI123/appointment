"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Users } from "lucide-react";
import { customerSelfService } from "@/services/customers";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";

export default function FamilyPage() {
  const orgs = useQuery({ queryKey: ["my-orgs"], queryFn: customerSelfService.organizations });
  const [chosen, setChosen] = useState("");
  const orgId = chosen || orgs.data?.[0]?.id || "";
  if (orgs.isLoading) return <Skeleton className="h-48" />;
  if (!orgs.data?.length) return <EmptyState icon={Users} title="No clinic yet" body="Family members and preferences are kept per clinic. Book an appointment first and come back here." />;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Family & preferences" description="Family members you book for and how each clinic may contact you." actions={orgs.data.length > 1 ? <NativeSelect aria-label="Clinic" className="w-56" value={orgId} onChange={(e) => setChosen(e.target.value)}>{orgs.data.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</NativeSelect> : null} />
      {orgId ? <><Dependents key={orgId} orgId={orgId} /><Preferences key={`${orgId}-p`} orgId={orgId} /></> : null}
    </div>
  );
}

function Dependents({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient();
  const deps = useQuery({ queryKey: ["my-dependents", orgId], queryFn: () => customerSelfService.dependents(orgId) });
  const [form, setForm] = useState({ full_name: "", relationship_label: "child", date_of_birth: "" });
  const add = useMutation({ mutationFn: () => customerSelfService.addDependent(orgId, { ...form, date_of_birth: form.date_of_birth || null }), onSuccess: () => { toast.success("Family member added"); setForm({ full_name: "", relationship_label: "child", date_of_birth: "" }); queryClient.invalidateQueries({ queryKey: ["my-dependents", orgId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: (id: string) => customerSelfService.removeDependent(orgId, id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["my-dependents", orgId] }), onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Card>
      <CardHeader><CardTitle>Family members</CardTitle><CardDescription>Choose them under &quot;Booking for&quot; when you book.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <form className="grid items-end gap-3 sm:grid-cols-[1fr_150px_160px_auto]" onSubmit={(e) => { e.preventDefault(); add.mutate(); }} data-testid="family-form">
          <Field label="Name" htmlFor="my_dep_name"><Input id="my_dep_name" required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
          <Field label="Relationship" htmlFor="my_dep_rel"><NativeSelect id="my_dep_rel" value={form.relationship_label} onChange={(e) => setForm({ ...form, relationship_label: e.target.value })}>{["child", "spouse", "parent", "sibling", "other"].map((r) => <option key={r} value={r}>{r}</option>)}</NativeSelect></Field>
          <Field label="Date of birth" htmlFor="my_dep_dob"><Input id="my_dep_dob" type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} /></Field>
          <Button type="submit" disabled={add.isPending}>Add</Button>
        </form>
        <ul className="divide-y rounded-lg border">{deps.data?.map((d) => <li key={d.id} className="flex items-center justify-between px-3 py-2 text-sm" data-testid="family-member"><span><span className="font-medium">{d.full_name}</span> <span className="text-muted-foreground">· {d.relationship_label}{d.date_of_birth ? ` · born ${formatDate(d.date_of_birth)}` : ""}</span></span><Button size="sm" variant="ghost" onClick={() => remove.mutate(d.id)}>Remove</Button></li>)}{deps.data?.length === 0 ? <li className="px-3 py-6 text-center text-sm text-muted-foreground">No family members yet.</li> : null}</ul>
      </CardContent>
    </Card>
  );
}

function Preferences({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["my-profile", orgId], queryFn: () => customerSelfService.profile(orgId) });
  const save = useMutation({ mutationFn: (body: Record<string, unknown>) => customerSelfService.updateProfile(orgId, body), onSuccess: () => { toast.success("Preferences saved"); queryClient.invalidateQueries({ queryKey: ["my-profile", orgId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  if (!profile.data) return null;
  const prefs = { sms: true, whatsapp: true, email: true, ...(profile.data.communication_preferences ?? {}) };
  const consent = { data_processing: false, marketing: false, ...(profile.data.consent ?? {}) };
  return (
    <Card>
      <CardHeader><CardTitle>Contact preferences & consent</CardTitle><CardDescription>Applies to this clinic only.</CardDescription></CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2">
        {([["sms", "SMS reminders"], ["whatsapp", "WhatsApp reminders"], ["email", "Email updates"]] as const).map(([k, l]) => <label key={k} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>{l}</span><Switch checked={prefs[k]} onCheckedChange={(v) => save.mutate({ communication_preferences: { ...prefs, [k]: v } })} /></label>)}
        <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Marketing messages</span><Switch checked={consent.marketing} onCheckedChange={(v) => save.mutate({ consent: { ...consent, marketing: v } })} /></label>
      </CardContent>
    </Card>
  );
}
