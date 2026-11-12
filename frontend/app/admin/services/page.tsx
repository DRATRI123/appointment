"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Briefcase, Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { MoneyInput } from "@/components/forms/money-input";
import { ImageUpload } from "@/components/forms/image-upload";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatPaise, omit } from "@/lib/utils";
import { titleCase } from "@/lib/format";
import type { Branch, Professional, Service, ServicePricing } from "@/types/catalog";

const PAYMENT_MODES: [Service["payment_mode"], string][] = [
  ["full_advance", "Full payment in advance"], ["partial_advance", "Partial advance"], ["optional_advance", "Advance optional"], ["pay_at_clinic", "Pay at clinic"], ["free", "Free"],
];

export default function ServicesPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("services:write");
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const services = useQuery({ queryKey: ["services", orgId, search], queryFn: () => catalogService.services({ search: search || undefined }), enabled: !!orgId });
  const [editing, setEditing] = useState<Service | "new" | null>(null);
  const invalidate = () => { queryClient.invalidateQueries({ queryKey: ["services", orgId] }); queryClient.invalidateQueries({ queryKey: ["categories", orgId] }); };
  const remove = useMutation({
    mutationFn: (id: string) => catalogService.deleteService(id),
    onSuccess: () => { toast.success("Service deleted"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Services" description="What customers book: duration, price, advance rules and where each service is offered." actions={<div className="flex gap-2"><Input placeholder="Search services" className="w-56" value={search} onChange={(e) => setSearch(e.target.value)} />{canWrite ? <Button onClick={() => setEditing("new")}><Plus /> Add service</Button> : null}</div>} />
      {services.isLoading ? <Skeleton className="h-48" /> : services.data?.length === 0 && !search ? (
        <EmptyState icon={Briefcase} title="No services yet" body="Create consultations, treatments or sessions. Prices are stored in paise and shown in rupees." action={canWrite ? <Button onClick={() => setEditing("new")}>Add service</Button> : undefined} />
      ) : (
        <Table>
          <TableHeader><TableRow><TableHead>Service</TableHead><TableHead>Category</TableHead><TableHead>Duration</TableHead><TableHead>Price</TableHead><TableHead>Payment</TableHead><TableHead>Status</TableHead>{canWrite ? <TableHead className="text-right">Actions</TableHead> : null}</TableRow></TableHeader>
          <TableBody>
            {services.data?.map((s) => (
              <TableRow key={s.id} data-testid="service-row">
                <TableCell className="font-medium">{s.name}{s.kind !== "standard" ? <Badge variant="outline" className="ml-2">{titleCase(s.kind)}</Badge> : null}</TableCell>
                <TableCell className="text-muted-foreground">{s.category_name ?? "—"}</TableCell>
                <TableCell>{s.duration_minutes} min</TableCell>
                <TableCell>{s.discounted_price_paise !== null ? <><span className="line-through text-muted-foreground mr-1">{formatPaise(s.price_paise)}</span>{formatPaise(s.discounted_price_paise)}</> : formatPaise(s.price_paise)}</TableCell>
                <TableCell className="text-muted-foreground">{titleCase(s.payment_mode)}</TableCell>
                <TableCell><Badge variant={s.is_active ? "success" : "destructive"}>{s.is_active ? "active" : "inactive"}</Badge>{!s.is_bookable_online ? <Badge variant="outline" className="ml-1">offline</Badge> : null}</TableCell>
                {canWrite ? <TableCell className="text-right"><Button size="sm" variant="ghost" onClick={() => setEditing(s)}>Edit</Button><Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Delete ${s.name}?`)) remove.mutate(s.id); }}>Delete</Button></TableCell> : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {editing ? <ServiceSheet service={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); invalidate(); }} /> : null}
    </div>
  );
}

type Draft = {
  name: string; kind: Service["kind"]; category_id: string; short_description: string; description: string; image_url: string | null;
  duration_minutes: number; buffer_minutes: number; consultation_mode: Service["consultation_mode"]; price_paise: number; discounted_price_paise: number | null;
  payment_mode: Service["payment_mode"]; advance_amount_paise: number | null; advance_percent: number | null; tax_percent: number;
  min_notice_minutes: number | null; max_advance_days: number | null; instructions: string; is_active: boolean; is_bookable_online: boolean; sort_order: number;
  pricing: ServicePricing[]; professional_ids: string[];
};

function toDraft(s: Service | null): Draft {
  return {
    name: s?.name ?? "", kind: s?.kind ?? "standard", category_id: s?.category_id ?? "", short_description: s?.short_description ?? "", description: s?.description ?? "", image_url: s?.image_url ?? null,
    duration_minutes: s?.duration_minutes ?? 15, buffer_minutes: s?.buffer_minutes ?? 0, consultation_mode: s?.consultation_mode ?? "in_person", price_paise: s?.price_paise ?? 0,
    discounted_price_paise: s?.discounted_price_paise ?? null, payment_mode: s?.payment_mode ?? "full_advance", advance_amount_paise: s?.advance_amount_paise ?? null, advance_percent: s?.advance_percent ?? null,
    tax_percent: s?.tax_percent ?? 0, min_notice_minutes: s?.min_notice_minutes ?? null, max_advance_days: s?.max_advance_days ?? null, instructions: s?.instructions ?? "",
    is_active: s?.is_active ?? true, is_bookable_online: s?.is_bookable_online ?? true, sort_order: s?.sort_order ?? 0, pricing: s?.pricing ?? [], professional_ids: s?.professional_ids ?? [],
  };
}

function ServiceSheet({ service, onClose, onSaved }: { service: Service | null; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(toDraft(service));
  const categories = useQuery({ queryKey: ["categories"], queryFn: catalogService.categories });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => catalogService.branches() });
  const professionals = useQuery({ queryKey: ["professionals"], queryFn: () => catalogService.professionals() });
  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...draft, category_id: draft.category_id || undefined, clear_category: service ? !draft.category_id : undefined,
        short_description: draft.short_description || null, description: draft.description || null, instructions: draft.instructions || null,
        pricing: draft.pricing.map((p) => omit(p, "branch_name")),
      };
      return service ? catalogService.updateService(service.id, body) : catalogService.createService(body);
    },
    onSuccess: () => { toast.success(service ? "Service updated" : "Service created"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const pricingFor = (b: Branch) => draft.pricing.find((p) => p.branch_id === b.id);
  const setPricing = (b: Branch, patch: Partial<ServicePricing> | null) => {
    const rest = draft.pricing.filter((p) => p.branch_id !== b.id);
    if (patch === null) return set("pricing", rest);
    const current = pricingFor(b) ?? { branch_id: b.id, price_paise: null, discounted_price_paise: null, advance_amount_paise: null, is_available: true };
    set("pricing", [...rest, { ...current, ...patch }]);
  };
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-3xl">
        <SheetHeader><SheetTitle>{service ? `Edit ${service.name}` : "New service"}</SheetTitle><SheetDescription>All amounts are stored in paise. Customers never set prices.</SheetDescription></SheetHeader>
        <form id="service-form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="service-form">
          <Tabs defaultValue="basics">
            <TabsList className="mb-4"><TabsTrigger value="basics">Basics</TabsTrigger><TabsTrigger value="pricing">Pricing &amp; payment</TabsTrigger><TabsTrigger value="branches">Branches</TabsTrigger><TabsTrigger value="professionals">Professionals</TabsTrigger><TabsTrigger value="rules">Rules</TabsTrigger></TabsList>
            <TabsContent value="basics" className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="s_name" className="sm:col-span-2"><Input id="s_name" required value={draft.name} onChange={(e) => set("name", e.target.value)} /></Field>
              <Field label="Category" htmlFor="s_cat"><NativeSelect id="s_cat" value={draft.category_id} onChange={(e) => set("category_id", e.target.value)}><option value="">— none —</option>{categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect></Field>
              <Field label="Type" htmlFor="s_kind"><NativeSelect id="s_kind" value={draft.kind} onChange={(e) => set("kind", e.target.value as Draft["kind"])}><option value="standard">Standard</option><option value="addon">Add-on</option><option value="follow_up">Follow-up</option></NativeSelect></Field>
              <Field label="Duration (minutes)" htmlFor="s_dur"><Input id="s_dur" type="number" min={5} value={draft.duration_minutes} onChange={(e) => set("duration_minutes", Number(e.target.value))} /></Field>
              <Field label="Buffer after (minutes)" htmlFor="s_buf"><Input id="s_buf" type="number" min={0} value={draft.buffer_minutes} onChange={(e) => set("buffer_minutes", Number(e.target.value))} /></Field>
              <Field label="Consultation mode" htmlFor="s_mode"><NativeSelect id="s_mode" value={draft.consultation_mode} onChange={(e) => set("consultation_mode", e.target.value as Draft["consultation_mode"])}><option value="in_person">In person</option><option value="online">Online / video</option><option value="both">Both</option></NativeSelect></Field>
              <Field label="Sort order" htmlFor="s_sort"><Input id="s_sort" type="number" value={draft.sort_order} onChange={(e) => set("sort_order", Number(e.target.value))} /></Field>
              <Field label="Short description" htmlFor="s_short" className="sm:col-span-2"><Input id="s_short" maxLength={255} value={draft.short_description} onChange={(e) => set("short_description", e.target.value)} /></Field>
              <Field label="Description" htmlFor="s_desc" className="sm:col-span-2"><Textarea id="s_desc" value={draft.description} onChange={(e) => set("description", e.target.value)} /></Field>
              <div className="sm:col-span-2"><ImageUpload label="Service image" shape="wide" value={draft.image_url} onChange={(v) => set("image_url", v)} /></div>
              <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Active</span><Switch checked={draft.is_active} onCheckedChange={(v) => set("is_active", v)} /></label>
              <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Bookable online</span><Switch checked={draft.is_bookable_online} onCheckedChange={(v) => set("is_bookable_online", v)} /></label>
            </TabsContent>
            <TabsContent value="pricing" className="grid gap-4 sm:grid-cols-2">
              <Field label="Price" htmlFor="s_price"><MoneyInput id="s_price" valuePaise={draft.price_paise} onChange={(v) => set("price_paise", v ?? 0)} /></Field>
              <Field label="Discounted price (optional)" htmlFor="s_disc"><MoneyInput id="s_disc" allowEmpty valuePaise={draft.discounted_price_paise} onChange={(v) => set("discounted_price_paise", v)} /></Field>
              <Field label="Payment mode" htmlFor="s_pay" className="sm:col-span-2"><NativeSelect id="s_pay" value={draft.payment_mode} onChange={(e) => set("payment_mode", e.target.value as Draft["payment_mode"])}>{PAYMENT_MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
              {draft.payment_mode === "partial_advance" || draft.payment_mode === "optional_advance" ? (
                <>
                  <Field label="Advance amount" htmlFor="s_adv"><MoneyInput id="s_adv" allowEmpty valuePaise={draft.advance_amount_paise} onChange={(v) => set("advance_amount_paise", v)} /></Field>
                  <Field label="or advance percent" htmlFor="s_advp"><Input id="s_advp" type="number" min={1} max={100} value={draft.advance_percent ?? ""} onChange={(e) => set("advance_percent", e.target.value ? Number(e.target.value) : null)} /></Field>
                </>
              ) : null}
              <Field label="Tax percent" htmlFor="s_tax"><Input id="s_tax" type="number" min={0} max={100} value={draft.tax_percent} onChange={(e) => set("tax_percent", Number(e.target.value))} /></Field>
            </TabsContent>
            <TabsContent value="branches" className="space-y-3">
              <p className="text-sm text-muted-foreground">Without an override a service is offered at every branch at its base price.</p>
              {branches.data?.map((b) => {
                const p = pricingFor(b);
                return (
                  <div key={b.id} className="grid items-end gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_140px_140px_auto]">
                    <div><p className="font-medium">{b.name}</p><p className="text-xs text-muted-foreground">{p ? (p.is_available ? "Custom pricing" : "Not offered here") : "Base price"}</p></div>
                    <Field label="Price override"><MoneyInput allowEmpty valuePaise={p?.price_paise ?? null} onChange={(v) => setPricing(b, { price_paise: v })} /></Field>
                    <Field label="Advance override"><MoneyInput allowEmpty valuePaise={p?.advance_amount_paise ?? null} onChange={(v) => setPricing(b, { advance_amount_paise: v })} /></Field>
                    <label className="flex items-center gap-2 pb-2 text-sm"><Switch checked={p ? p.is_available : true} onCheckedChange={(v) => setPricing(b, { is_available: v })} /> Offered</label>
                  </div>
                );
              })}
            </TabsContent>
            <TabsContent value="professionals" className="space-y-2">
              <p className="text-sm text-muted-foreground">Who can perform this service. Per-branch fee overrides live on the professional.</p>
              {professionals.data?.length === 0 ? <p className="text-sm">No professionals yet. Add them under Professionals.</p> : null}
              {professionals.data?.map((pr: Professional) => (
                <label key={pr.id} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm">
                  <Checkbox checked={draft.professional_ids.includes(pr.id)} onCheckedChange={(v) => set("professional_ids", v ? [...draft.professional_ids, pr.id] : draft.professional_ids.filter((x) => x !== pr.id))} />
                  <span className="font-medium">{pr.display_name}</span><span className="text-muted-foreground">{pr.specialization}</span>
                </label>
              ))}
            </TabsContent>
            <TabsContent value="rules" className="grid gap-4 sm:grid-cols-2">
              <Field label="Minimum notice (minutes)" htmlFor="s_notice" hint="Blank = organization default"><Input id="s_notice" type="number" min={0} value={draft.min_notice_minutes ?? ""} onChange={(e) => set("min_notice_minutes", e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Max advance booking (days)" htmlFor="s_adv_days" hint="Blank = organization default"><Input id="s_adv_days" type="number" min={1} value={draft.max_advance_days ?? ""} onChange={(e) => set("max_advance_days", e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Instructions for customers" htmlFor="s_instr" className="sm:col-span-2"><Textarea id="s_instr" placeholder="Come fasting, bring previous reports…" value={draft.instructions} onChange={(e) => set("instructions", e.target.value)} /></Field>
            </TabsContent>
          </Tabs>
        </form>
        <SheetFooter><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" form="service-form" disabled={save.isPending}>{service ? "Save changes" : "Create service"}</Button></SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
