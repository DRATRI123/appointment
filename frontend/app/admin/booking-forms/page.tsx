"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileSpreadsheet, Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { formsService } from "@/services/customers";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";

export default function BookingFormsPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("booking_forms:write");
  const queryClient = useQueryClient();
  const forms = useQuery({ queryKey: ["forms", orgId], queryFn: () => formsService.list(), enabled: !!orgId });
  const services = useQuery({ queryKey: ["services-all"], queryFn: () => catalogService.services(), enabled: !!orgId });
  const [creating, setCreating] = useState(false);
  const assign = useMutation({ mutationFn: ({ service_id, form_id }: { service_id: string; form_id: string | null }) => formsService.assign(service_id, form_id), onSuccess: (r) => { toast.success(r.detail); queryClient.invalidateQueries({ queryKey: ["forms"] }); queryClient.invalidateQueries({ queryKey: ["services-all"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const published = (forms.data ?? []).filter((f) => f.is_published && !f.is_template);
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader title="Booking forms" description="Ask customers the right questions at booking time. Forms are versioned: editing a published form creates a new draft." actions={canWrite ? <Button onClick={() => setCreating(true)}><Plus /> New form</Button> : null} />
      {forms.isLoading ? <Skeleton className="h-48" /> : forms.data?.length === 0 ? (
        <EmptyState icon={FileSpreadsheet} title="No booking forms yet" body="Start from a template such as Patient intake or build your own fields." action={canWrite ? <Button onClick={() => setCreating(true)}>New form</Button> : undefined} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {forms.data?.map((f) => (
            <Card key={f.id} data-testid="form-card" className="gap-3 py-5">
              <CardHeader>
                <div className="flex items-start justify-between gap-2"><CardTitle><Link href={`/admin/booking-forms/${f.id}`} className="hover:underline">{f.name}</Link></CardTitle><div className="flex gap-1"><Badge variant="outline">v{f.version}</Badge>{f.is_template ? <Badge variant="secondary">template</Badge> : f.is_published ? <Badge variant="success">published</Badge> : <Badge variant="warning">draft</Badge>}</div></div>
                <CardDescription>{f.description || `${f.fields.length} field${f.fields.length === 1 ? "" : "s"}`} · {f.scope === "organization" ? "default for all services" : f.scope === "branch" ? "branch default" : "service-specific"}</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between text-xs text-muted-foreground"><span>{f.fields.length} fields · {f.service_count} services · {f.response_count} responses</span><Button asChild size="sm" variant="outline"><Link href={`/admin/booking-forms/${f.id}`}>Open builder</Link></Button></CardContent>
            </Card>
          ))}
        </div>
      )}
      {canWrite && services.data?.length ? (
        <Card>
          <CardHeader><CardTitle>Which form does each service use?</CardTitle><CardDescription>Service-specific form → branch form → organization default. Leave blank to inherit.</CardDescription></CardHeader>
          <CardContent><ul className="divide-y">{services.data.map((s) => <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-sm"><span>{s.name}</span><NativeSelect className="w-64" defaultValue="" onChange={(e) => assign.mutate({ service_id: s.id, form_id: e.target.value || null })}><option value="">Inherit default</option>{published.map((f) => <option key={f.id} value={f.id}>{f.name} (v{f.version})</option>)}</NativeSelect></li>)}</ul></CardContent>
        </Card>
      ) : null}
      {creating ? <NewFormDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function NewFormDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const templates = useQuery({ queryKey: ["form-templates"], queryFn: formsService.templates });
  const [form, setForm] = useState({ name: "", scope: "organization", clone_from: "" });
  const create = useMutation({ mutationFn: () => formsService.create({ name: form.name, scope: form.scope, clone_from: form.clone_from || undefined }), onSuccess: (f) => { toast.success("Form created"); queryClient.invalidateQueries({ queryKey: ["forms"] }); router.push(`/admin/booking-forms/${f.id}`); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>New booking form</DialogTitle><DialogDescription>Start blank or from a template. You can edit every field afterwards.</DialogDescription></DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} data-testid="new-form">
          <Field label="Name" htmlFor="nf_name"><Input id="nf_name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Applies to" htmlFor="nf_scope"><NativeSelect id="nf_scope" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}><option value="organization">All services (organization default)</option><option value="service">Specific services (assign later)</option></NativeSelect></Field>
          <Field label="Start from" htmlFor="nf_tpl"><NativeSelect id="nf_tpl" value={form.clone_from} onChange={(e) => setForm({ ...form, clone_from: e.target.value })}><option value="">Blank form</option>{templates.data?.map((t) => <option key={t.slug} value={t.slug}>{t.name} — {t.description}</option>)}</NativeSelect></Field>
          <DialogFooter><Button type="submit" disabled={create.isPending}>Create</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
