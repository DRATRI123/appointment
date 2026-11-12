"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Building2, Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Field } from "@/components/forms/field";
import { BusinessHoursEditor } from "@/components/forms/business-hours-editor";
import { ImageUpload } from "@/components/forms/image-upload";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import type { Branch, BusinessHours } from "@/types/catalog";

const DEFAULT_HOURS: BusinessHours = { mon: [["09:00", "18:00"]], tue: [["09:00", "18:00"]], wed: [["09:00", "18:00"]], thu: [["09:00", "18:00"]], fri: [["09:00", "18:00"]], sat: [["09:00", "14:00"]] };

type Draft = {
  name: string; code: string; phone: string; email: string; description: string; image_url: string | null;
  address: { line1: string; line2: string; city: string; state: string; pincode: string }; business_hours: BusinessHours; is_active: boolean; is_default: boolean;
};

const empty: Draft = { name: "", code: "", phone: "", email: "", description: "", image_url: null, address: { line1: "", line2: "", city: "", state: "", pincode: "" }, business_hours: DEFAULT_HOURS, is_active: true, is_default: false };

function toDraft(b: Branch): Draft {
  const a = (b.address ?? {}) as Record<string, string>;
  return {
    name: b.name, code: b.code, phone: b.phone ?? "", email: b.email ?? "", description: b.description ?? "", image_url: b.image_url,
    address: { line1: a.line1 ?? "", line2: a.line2 ?? "", city: a.city ?? "", state: a.state ?? "", pincode: a.pincode ?? "" },
    business_hours: b.business_hours ?? {}, is_active: b.is_active, is_default: b.is_default,
  };
}

export default function BranchesPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("branches:write");
  const queryClient = useQueryClient();
  const branches = useQuery({ queryKey: ["branches", orgId], queryFn: () => catalogService.branches(), enabled: !!orgId });
  const [editing, setEditing] = useState<Branch | "new" | null>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["branches", orgId] });
  const remove = useMutation({
    mutationFn: (id: string) => catalogService.deleteBranch(id),
    onSuccess: () => { toast.success("Branch deleted"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Branches" description="Locations where appointments happen. Each has its own hours, contact details and, later, UPI account." actions={canWrite ? <Button onClick={() => setEditing("new")}><Plus /> Add branch</Button> : null} />
      {branches.isLoading ? <Skeleton className="h-48" /> : branches.data?.length === 0 ? (
        <EmptyState icon={Building2} title="No branches yet" body="Add your first location. Professionals, services and bookings are attached to branches." action={canWrite ? <Button onClick={() => setEditing("new")}>Add branch</Button> : undefined} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {branches.data?.map((b) => (
            <Card key={b.id} data-testid="branch-card" className="gap-3">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="flex items-center gap-2">{b.name} <Badge variant="outline">{b.code}</Badge></CardTitle>
                    <CardDescription>{[(b.address as Record<string, string> | null)?.city, b.phone].filter(Boolean).join(" · ") || "No contact details yet"}</CardDescription>
                  </div>
                  <div className="flex gap-1">
                    {b.is_default ? <Badge variant="secondary">default</Badge> : null}
                    <Badge variant={b.is_active ? "success" : "destructive"}>{b.is_active ? "active" : "inactive"}</Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{b.business_hours ? `${Object.keys(b.business_hours).length} open days` : "Hours not set"}</span>
                {canWrite ? (
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => setEditing(b)}>Edit</Button>
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Delete ${b.name}?`)) remove.mutate(b.id); }}>Delete</Button>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {editing ? <BranchSheet branch={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); invalidate(); }} /> : null}
    </div>
  );
}

function BranchSheet({ branch, onClose, onSaved }: { branch: Branch | null; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(branch ? toDraft(branch) : empty);
  const save = useMutation({
    mutationFn: () => {
      const body = { ...draft, phone: draft.phone || null, email: draft.email || null, description: draft.description || null, business_hours: Object.keys(draft.business_hours).length ? draft.business_hours : null };
      return branch ? catalogService.updateBranch(branch.id, body) : catalogService.createBranch(body);
    },
    onSuccess: () => { toast.success(branch ? "Branch updated" : "Branch created"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft({ ...draft, [k]: v });
  const setAddr = (k: keyof Draft["address"], v: string) => setDraft({ ...draft, address: { ...draft.address, [k]: v } });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{branch ? `Edit ${branch.name}` : "New branch"}</SheetTitle>
          <SheetDescription>Business hours drive availability for professionals who work here.</SheetDescription>
        </SheetHeader>
        <form id="branch-form" className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="branch-form">
          <Field label="Name" htmlFor="b_name" className="sm:col-span-2"><Input id="b_name" required value={draft.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Code" htmlFor="b_code" hint="Short identifier, e.g. MAIN"><Input id="b_code" required value={draft.code} onChange={(e) => set("code", e.target.value.toUpperCase())} /></Field>
          <Field label="Phone" htmlFor="b_phone"><Input id="b_phone" value={draft.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
          <Field label="Email" htmlFor="b_email" className="sm:col-span-2"><Input id="b_email" type="email" value={draft.email} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label="Address line 1" htmlFor="b_l1" className="sm:col-span-2"><Input id="b_l1" value={draft.address.line1} onChange={(e) => setAddr("line1", e.target.value)} /></Field>
          <Field label="Address line 2" htmlFor="b_l2" className="sm:col-span-2"><Input id="b_l2" value={draft.address.line2} onChange={(e) => setAddr("line2", e.target.value)} /></Field>
          <Field label="City" htmlFor="b_city"><Input id="b_city" value={draft.address.city} onChange={(e) => setAddr("city", e.target.value)} /></Field>
          <Field label="State" htmlFor="b_state"><Input id="b_state" value={draft.address.state} onChange={(e) => setAddr("state", e.target.value)} /></Field>
          <Field label="PIN code" htmlFor="b_pin"><Input id="b_pin" value={draft.address.pincode} onChange={(e) => setAddr("pincode", e.target.value)} /></Field>
          <div className="sm:col-span-2"><ImageUpload label="Branch photo" shape="wide" value={draft.image_url} onChange={(v) => set("image_url", v)} /></div>
          <Field label="Description" htmlFor="b_desc" className="sm:col-span-2"><Textarea id="b_desc" value={draft.description} onChange={(e) => set("description", e.target.value)} /></Field>
          <div className="sm:col-span-2 space-y-2">
            <p className="text-sm font-medium">Business hours</p>
            <BusinessHoursEditor value={draft.business_hours} onChange={(v) => set("business_hours", v)} />
          </div>
          <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Active</span><Switch checked={draft.is_active} onCheckedChange={(v) => set("is_active", v)} /></label>
          <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Default branch</span><Switch checked={draft.is_default} onCheckedChange={(v) => set("is_default", v)} /></label>
        </form>
        <SheetFooter>
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="branch-form" disabled={save.isPending}>{branch ? "Save changes" : "Create branch"}</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
