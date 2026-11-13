"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, TicketPercent } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { couponsService } from "@/services/payments";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { MoneyInput } from "@/components/forms/money-input";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { formatPaise } from "@/lib/utils";

export default function CouponsPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("services:write");
  const queryClient = useQueryClient();
  const coupons = useQuery({ queryKey: ["coupons", orgId], queryFn: couponsService.list, enabled: !!orgId });
  const [creating, setCreating] = useState(false);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["coupons", orgId] });
  const toggle = useMutation({ mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => couponsService.update(id, { is_active }), onSuccess: invalidate, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: (id: string) => couponsService.remove(id), onSuccess: () => { toast.success("Coupon deleted"); invalidate(); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Coupons" description="Discount codes customers enter while booking. The discount is applied by the server before tax." actions={canWrite ? <Button onClick={() => setCreating(true)}><Plus /> New coupon</Button> : null} />
      {coupons.isLoading ? <Skeleton className="h-48" /> : coupons.data?.length === 0 ? <EmptyState icon={TicketPercent} title="No coupons" body="Create a launch offer, a follow-up discount or a 100% free-camp code." action={canWrite ? <Button onClick={() => setCreating(true)}>New coupon</Button> : undefined} /> : (
        <Table>
          <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Discount</TableHead><TableHead>Limits</TableHead><TableHead>Valid</TableHead><TableHead>Used</TableHead><TableHead>Active</TableHead>{canWrite ? <TableHead /> : null}</TableRow></TableHeader>
          <TableBody>
            {coupons.data?.map((c) => (
              <TableRow key={c.id} data-testid="coupon-row">
                <TableCell><span className="font-mono font-semibold">{c.code}</span>{c.description ? <span className="block text-xs text-muted-foreground">{c.description}</span> : null}</TableCell>
                <TableCell>{c.discount_type === "percent" ? `${c.discount_value}%` : formatPaise(c.discount_value)}{c.max_discount_paise ? <span className="block text-xs text-muted-foreground">up to {formatPaise(c.max_discount_paise)}</span> : null}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{[c.min_amount_paise ? `min ${formatPaise(c.min_amount_paise)}` : null, c.per_customer_limit ? `${c.per_customer_limit}/customer` : null, c.service_ids?.length ? `${c.service_ids.length} service(s)` : "all services"].filter(Boolean).join(" · ")}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{c.valid_from ? formatDate(c.valid_from) : "now"} → {c.valid_to ? formatDate(c.valid_to) : "no end"}</TableCell>
                <TableCell>{c.redemptions}{c.max_redemptions ? ` / ${c.max_redemptions}` : ""}</TableCell>
                <TableCell><Switch checked={c.is_active} disabled={!canWrite} onCheckedChange={(v) => toggle.mutate({ id: c.id, is_active: v })} /></TableCell>
                {canWrite ? <TableCell className="text-right"><Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Delete ${c.code}?`)) remove.mutate(c.id); }}>Delete</Button></TableCell> : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {creating ? <CouponDialog onClose={() => setCreating(false)} onSaved={() => { setCreating(false); invalidate(); }} /> : null}
    </div>
  );
}

function CouponDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const services = useQuery({ queryKey: ["services-all"], queryFn: () => catalogService.services() });
  const [form, setForm] = useState({ code: "", description: "", discount_type: "percent", percent: 10, flat: 10000 as number | null, max_discount_paise: null as number | null, min_amount_paise: null as number | null, valid_to: "", max_redemptions: "", per_customer_limit: "1", service_ids: [] as string[] });
  const create = useMutation({
    mutationFn: () => couponsService.create({
      code: form.code, description: form.description || null, discount_type: form.discount_type, discount_value: form.discount_type === "percent" ? form.percent : form.flat,
      max_discount_paise: form.discount_type === "percent" ? form.max_discount_paise : null, min_amount_paise: form.min_amount_paise, valid_to: form.valid_to ? new Date(`${form.valid_to}T23:59:59`).toISOString() : null,
      max_redemptions: form.max_redemptions ? Number(form.max_redemptions) : null, per_customer_limit: form.per_customer_limit ? Number(form.per_customer_limit) : null, service_ids: form.service_ids.length ? form.service_ids : null,
    }),
    onSuccess: () => { toast.success("Coupon created"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader><DialogTitle>New coupon</DialogTitle><DialogDescription>Redemptions are counted from bookings; a cancelled or expired booking gives the redemption back.</DialogDescription></DialogHeader>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} data-testid="coupon-form">
          <Field label="Code" htmlFor="cp_code"><Input id="cp_code" required minLength={3} className="font-mono uppercase" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "") })} /></Field>
          <Field label="Type" htmlFor="cp_type"><NativeSelect id="cp_type" value={form.discount_type} onChange={(e) => setForm({ ...form, discount_type: e.target.value })}><option value="percent">Percent off</option><option value="flat">Flat amount off</option></NativeSelect></Field>
          {form.discount_type === "percent" ? (<>
            <Field label="Percent" htmlFor="cp_pct"><Input id="cp_pct" type="number" min={1} max={100} value={form.percent} onChange={(e) => setForm({ ...form, percent: Number(e.target.value) })} /></Field>
            <Field label="Maximum discount (optional)" htmlFor="cp_max"><MoneyInput id="cp_max" allowEmpty valuePaise={form.max_discount_paise} onChange={(v) => setForm({ ...form, max_discount_paise: v })} /></Field>
          </>) : <Field label="Amount off" htmlFor="cp_flat" className="sm:col-span-2"><MoneyInput id="cp_flat" valuePaise={form.flat} onChange={(v) => setForm({ ...form, flat: v })} /></Field>}
          <Field label="Minimum booking amount" htmlFor="cp_min"><MoneyInput id="cp_min" allowEmpty valuePaise={form.min_amount_paise} onChange={(v) => setForm({ ...form, min_amount_paise: v })} /></Field>
          <Field label="Valid until" htmlFor="cp_to"><Input id="cp_to" type="date" value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} /></Field>
          <Field label="Total uses (blank = unlimited)" htmlFor="cp_total"><Input id="cp_total" type="number" min={1} value={form.max_redemptions} onChange={(e) => setForm({ ...form, max_redemptions: e.target.value })} /></Field>
          <Field label="Uses per customer" htmlFor="cp_per"><Input id="cp_per" type="number" min={1} value={form.per_customer_limit} onChange={(e) => setForm({ ...form, per_customer_limit: e.target.value })} /></Field>
          <Field label="Description" htmlFor="cp_desc" className="sm:col-span-2"><Input id="cp_desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <div className="space-y-2 sm:col-span-2"><p className="text-sm font-medium">Only for these services (none = all)</p><div className="flex flex-wrap gap-2">{services.data?.map((s) => <label key={s.id} className="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm"><Checkbox checked={form.service_ids.includes(s.id)} onCheckedChange={(v) => setForm({ ...form, service_ids: v ? [...form.service_ids, s.id] : form.service_ids.filter((x) => x !== s.id) })} />{s.name}</label>)}</div></div>
          <DialogFooter className="sm:col-span-2"><Badge variant="outline" className="mr-auto">Applied before tax</Badge><Button type="submit" disabled={create.isPending || form.code.length < 3}>Create coupon</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
