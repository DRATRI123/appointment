"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Stethoscope } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService, mediaUrl } from "@/services/catalog";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { Card, CardContent } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { MoneyInput } from "@/components/forms/money-input";
import { ImageUpload } from "@/components/forms/image-upload";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatPaise, omit } from "@/lib/utils";
import type { Professional, ProfessionalBranch, ProfessionalServiceLink } from "@/types/catalog";

export default function ProfessionalsPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("professionals:write");
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const pros = useQuery({ queryKey: ["professionals", orgId, search], queryFn: () => catalogService.professionals({ search: search || undefined }), enabled: !!orgId });
  const [editing, setEditing] = useState<Professional | "new" | null>(null);
  const invalidate = () => { queryClient.invalidateQueries({ queryKey: ["professionals"] }); queryClient.invalidateQueries({ queryKey: ["services"] }); };
  const remove = useMutation({
    mutationFn: (id: string) => catalogService.deleteProfessional(id),
    onSuccess: () => { toast.success("Professional removed"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Professionals" description="Doctors, therapists and consultants. Each can work at several branches with different fees and durations." actions={<div className="flex gap-2"><Input placeholder="Search name or specialization" className="w-64" value={search} onChange={(e) => setSearch(e.target.value)} />{canWrite ? <Button onClick={() => setEditing("new")}><Plus /> Add professional</Button> : null}</div>} />
      {pros.isLoading ? <Skeleton className="h-48" /> : pros.data?.length === 0 && !search ? (
        <EmptyState icon={Stethoscope} title="No professionals yet" body="Add the people customers book with, then assign branches and services." action={canWrite ? <Button onClick={() => setEditing("new")}>Add professional</Button> : undefined} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {pros.data?.map((p) => (
            <Card key={p.id} data-testid="professional-card" className="py-5">
              <CardContent className="flex gap-4">
                <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-full bg-accent text-lg font-semibold text-accent-foreground">
                  {p.profile_photo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={mediaUrl(p.profile_photo_url)} alt="" className="h-full w-full object-cover" />
                  ) : p.display_name.split(" ").filter((x) => !x.endsWith(".")).slice(0, 2).map((x) => x[0]).join("")}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0"><p className="truncate font-semibold">{p.display_name}</p><p className="truncate text-sm text-muted-foreground">{[p.specialization, p.qualification].filter(Boolean).join(" · ") || "No specialization"}</p></div>
                    <Badge variant={p.is_active ? "success" : "destructive"}>{p.is_active ? "active" : "inactive"}</Badge>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{p.branches.length} branch{p.branches.length === 1 ? "" : "es"} · {p.services.length} service{p.services.length === 1 ? "" : "s"}{p.default_fee_paise !== null ? ` · from ${formatPaise(p.default_fee_paise)}` : ""}</p>
                  {canWrite ? <div className="mt-3 flex gap-1"><Button size="sm" variant="outline" onClick={() => setEditing(p)}>Edit</Button><Button asChild size="sm" variant="ghost"><Link href={`/admin/schedules?professional=${p.id}`}>Schedule</Link></Button><Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Remove ${p.display_name}?`)) remove.mutate(p.id); }}>Remove</Button></div> : null}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {editing ? <ProfessionalSheet pro={editing === "new" ? null : editing} orgId={orgId!} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); invalidate(); }} /> : null}
    </div>
  );
}

type Draft = {
  display_name: string; title: string; specialization: string; qualification: string; experience_years: number | null; registration_number: string; registration_council: string;
  biography: string; languages: string; email: string; phone: string; profile_photo_url: string | null; default_fee_paise: number | null; default_duration_minutes: number; buffer_minutes: number;
  slot_capacity: number; is_active: boolean; is_bookable_online: boolean; user_id: string; branches: ProfessionalBranch[]; services: ProfessionalServiceLink[];
};

function toDraft(p: Professional | null): Draft {
  return {
    display_name: p?.display_name ?? "", title: p?.title ?? "Dr.", specialization: p?.specialization ?? "", qualification: p?.qualification ?? "", experience_years: p?.experience_years ?? null,
    registration_number: p?.registration_number ?? "", registration_council: p?.registration_council ?? "", biography: p?.biography ?? "", languages: (p?.languages ?? []).join(", "),
    email: p?.email ?? "", phone: p?.phone ?? "", profile_photo_url: p?.profile_photo_url ?? null, default_fee_paise: p?.default_fee_paise ?? null, default_duration_minutes: p?.default_duration_minutes ?? 15,
    buffer_minutes: p?.buffer_minutes ?? 0, slot_capacity: p?.slot_capacity ?? 1, is_active: p?.is_active ?? true, is_bookable_online: p?.is_bookable_online ?? true, user_id: p?.user_id ?? "",
    branches: p?.branches ?? [], services: p?.services ?? [],
  };
}

function ProfessionalSheet({ pro, orgId, onClose, onSaved }: { pro: Professional | null; orgId: string; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(toDraft(pro));
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => catalogService.branches() });
  const services = useQuery({ queryKey: ["services-all"], queryFn: () => catalogService.services() });
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => organizationsService.members(orgId) });
  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...draft, title: draft.title || null, specialization: draft.specialization || null, qualification: draft.qualification || null, registration_number: draft.registration_number || null,
        registration_council: draft.registration_council || null, biography: draft.biography || null, email: draft.email || null, phone: draft.phone || null,
        languages: draft.languages.split(",").map((s) => s.trim()).filter(Boolean), user_id: draft.user_id || undefined, clear_user: pro ? !draft.user_id : undefined,
        branches: draft.branches.map((x) => omit(x, "branch_name")), services: draft.services.map((x) => omit(x, "service_name")),
      };
      return pro ? catalogService.updateProfessional(pro.id, body) : catalogService.createProfessional(body);
    },
    onSuccess: () => { toast.success(pro ? "Professional updated" : "Professional added"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const staffMembers = members.data ?? [];
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-3xl">
        <SheetHeader><SheetTitle>{pro ? `Edit ${pro.display_name}` : "New professional"}</SheetTitle><SheetDescription>Branch assignments carry their own fee, duration and buffer.</SheetDescription></SheetHeader>
        <form id="pro-form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="professional-form">
          <Tabs defaultValue="profile">
            <TabsList className="mb-4"><TabsTrigger value="profile">Profile</TabsTrigger><TabsTrigger value="branches">Branches &amp; fees</TabsTrigger><TabsTrigger value="services">Services</TabsTrigger><TabsTrigger value="account">Account</TabsTrigger></TabsList>
            <TabsContent value="profile" className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2"><ImageUpload label="Profile photo" shape="circle" value={draft.profile_photo_url} onChange={(v) => set("profile_photo_url", v)} /></div>
              <Field label="Title" htmlFor="p_title"><Input id="p_title" placeholder="Dr." value={draft.title} onChange={(e) => set("title", e.target.value)} /></Field>
              <Field label="Display name" htmlFor="p_name"><Input id="p_name" required value={draft.display_name} onChange={(e) => set("display_name", e.target.value)} /></Field>
              <Field label="Specialization" htmlFor="p_spec"><Input id="p_spec" placeholder="Dermatology" value={draft.specialization} onChange={(e) => set("specialization", e.target.value)} /></Field>
              <Field label="Qualification" htmlFor="p_qual"><Input id="p_qual" placeholder="MBBS, MD" value={draft.qualification} onChange={(e) => set("qualification", e.target.value)} /></Field>
              <Field label="Experience (years)" htmlFor="p_exp"><Input id="p_exp" type="number" min={0} value={draft.experience_years ?? ""} onChange={(e) => set("experience_years", e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Languages" htmlFor="p_lang" hint="Comma separated"><Input id="p_lang" placeholder="English, Hindi, Gujarati" value={draft.languages} onChange={(e) => set("languages", e.target.value)} /></Field>
              <Field label="Registration number" htmlFor="p_reg"><Input id="p_reg" value={draft.registration_number} onChange={(e) => set("registration_number", e.target.value)} /></Field>
              <Field label="Registration council" htmlFor="p_council"><Input id="p_council" value={draft.registration_council} onChange={(e) => set("registration_council", e.target.value)} /></Field>
              <Field label="Biography" htmlFor="p_bio" className="sm:col-span-2"><Textarea id="p_bio" value={draft.biography} onChange={(e) => set("biography", e.target.value)} /></Field>
              <Field label="Default fee" htmlFor="p_fee"><MoneyInput id="p_fee" allowEmpty valuePaise={draft.default_fee_paise} onChange={(v) => set("default_fee_paise", v)} /></Field>
              <Field label="Default slot (minutes)" htmlFor="p_dur"><Input id="p_dur" type="number" min={5} value={draft.default_duration_minutes} onChange={(e) => set("default_duration_minutes", Number(e.target.value))} /></Field>
              <Field label="Buffer between appointments (minutes)" htmlFor="p_buf"><Input id="p_buf" type="number" min={0} value={draft.buffer_minutes} onChange={(e) => set("buffer_minutes", Number(e.target.value))} /></Field>
              <Field label="Patients per slot" htmlFor="p_cap"><Input id="p_cap" type="number" min={1} value={draft.slot_capacity} onChange={(e) => set("slot_capacity", Number(e.target.value))} /></Field>
              <Field label="Contact email" htmlFor="p_email"><Input id="p_email" type="email" value={draft.email} onChange={(e) => set("email", e.target.value)} /></Field>
              <Field label="Contact phone" htmlFor="p_phone"><Input id="p_phone" value={draft.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
              <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Active</span><Switch checked={draft.is_active} onCheckedChange={(v) => set("is_active", v)} /></label>
              <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Bookable online</span><Switch checked={draft.is_bookable_online} onCheckedChange={(v) => set("is_bookable_online", v)} /></label>
            </TabsContent>
            <TabsContent value="branches" className="space-y-3">
              {branches.data?.length === 0 ? <p className="text-sm text-muted-foreground">Create a branch first.</p> : null}
              {branches.data?.map((b) => {
                const row = draft.branches.find((x) => x.branch_id === b.id);
                return (
                  <div key={b.id} className="rounded-lg border p-3">
                    <label className="flex items-center gap-3 text-sm font-medium"><Checkbox checked={!!row} onCheckedChange={(v) => set("branches", v ? [...draft.branches, { branch_id: b.id, fee_paise: draft.default_fee_paise, duration_minutes: null, buffer_minutes: null, room_label: null, is_active: true }] : draft.branches.filter((x) => x.branch_id !== b.id))} />{b.name}</label>
                    {row ? (
                      <div className="mt-3 grid gap-3 sm:grid-cols-4">
                        <Field label="Fee here"><MoneyInput allowEmpty valuePaise={row.fee_paise} onChange={(v) => set("branches", draft.branches.map((x) => x.branch_id === b.id ? { ...x, fee_paise: v } : x))} /></Field>
                        <Field label="Slot minutes"><Input type="number" min={5} placeholder="default" value={row.duration_minutes ?? ""} onChange={(e) => set("branches", draft.branches.map((x) => x.branch_id === b.id ? { ...x, duration_minutes: e.target.value ? Number(e.target.value) : null } : x))} /></Field>
                        <Field label="Buffer minutes"><Input type="number" min={0} placeholder="default" value={row.buffer_minutes ?? ""} onChange={(e) => set("branches", draft.branches.map((x) => x.branch_id === b.id ? { ...x, buffer_minutes: e.target.value ? Number(e.target.value) : null } : x))} /></Field>
                        <Field label="Room"><Input placeholder="Room 2" value={row.room_label ?? ""} onChange={(e) => set("branches", draft.branches.map((x) => x.branch_id === b.id ? { ...x, room_label: e.target.value || null } : x))} /></Field>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </TabsContent>
            <TabsContent value="services" className="space-y-2">
              {services.data?.length === 0 ? <p className="text-sm text-muted-foreground">Create services first.</p> : null}
              {services.data?.map((s) => {
                const row = draft.services.find((x) => x.service_id === s.id && !x.branch_id);
                return (
                  <div key={s.id} className="flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-sm">
                    <label className="flex flex-1 items-center gap-3"><Checkbox checked={!!row} onCheckedChange={(v) => set("services", v ? [...draft.services, { service_id: s.id, branch_id: null, fee_override_paise: null, duration_override_minutes: null, is_active: true }] : draft.services.filter((x) => !(x.service_id === s.id && !x.branch_id)))} /><span className="font-medium">{s.name}</span><span className="text-muted-foreground">{formatPaise(s.price_paise)} · {s.duration_minutes} min</span></label>
                    {row ? <div className="w-36"><MoneyInput allowEmpty placeholder="fee override" valuePaise={row.fee_override_paise} onChange={(v) => set("services", draft.services.map((x) => x === row ? { ...x, fee_override_paise: v } : x))} /></div> : null}
                  </div>
                );
              })}
            </TabsContent>
            <TabsContent value="account" className="space-y-4">
              <p className="text-sm text-muted-foreground">Link a staff account so this professional can sign in to their own dashboard. Add them under Staff with the Doctor or Professional role first.</p>
              <Field label="Staff account" htmlFor="p_user">
                <NativeSelect id="p_user" value={draft.user_id} onChange={(e) => set("user_id", e.target.value)}>
                  <option value="">— not linked —</option>
                  {staffMembers.map((m) => <option key={m.id} value={m.user.id}>{m.user.full_name} · {m.role_name}</option>)}
                </NativeSelect>
              </Field>
            </TabsContent>
          </Tabs>
        </form>
        <SheetFooter><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" form="pro-form" disabled={save.isPending}>{pro ? "Save changes" : "Add professional"}</Button></SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
