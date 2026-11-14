"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MoneyInput } from "@/components/forms/money-input";
import { errorMessage } from "@/lib/errors";
import { formatPaise } from "@/lib/utils";
import { LIMIT_LABEL, SUBSCRIPTION_STATUS_LABEL, type Plan } from "@/types/platform";

const LIMITS = Object.keys(LIMIT_LABEL) as (keyof typeof LIMIT_LABEL)[];

function PlansEditor({ initial }: { initial: Plan[] }) {
  const queryClient = useQueryClient();
  const [plans, setPlans] = useState<Plan[]>(initial);
  const set = (i: number, patch: Partial<Plan>) => setPlans((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const save = useMutation({ mutationFn: () => platformService.savePlans(plans), onSuccess: () => { toast.success("Plans saved"); queryClient.invalidateQueries({ queryKey: ["platform-plans"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Plans</CardTitle><CardDescription>Empty limit = unlimited. Changing a plan here does not change organizations already on it; record a plan change to apply new limits.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <Table className="text-sm" data-testid="plans-table">
          <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Price</TableHead><TableHead>Cycle</TableHead>{LIMITS.map((l) => <TableHead key={l}>{LIMIT_LABEL[l]}</TableHead>)}<TableHead>Offered</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {plans.map((p, i) => (
              <TableRow key={i}>
                <TableCell><Input aria-label="Plan code" className="w-28 font-mono text-xs" value={p.code} onChange={(e) => set(i, { code: e.target.value.toLowerCase() })} /></TableCell>
                <TableCell><Input aria-label="Plan name" className="w-32" value={p.name} onChange={(e) => set(i, { name: e.target.value })} /></TableCell>
                <TableCell className="w-32"><MoneyInput valuePaise={p.price_paise} onChange={(v) => set(i, { price_paise: v ?? 0 })} /></TableCell>
                <TableCell><NativeSelect aria-label="Billing cycle" value={p.billing_cycle} onChange={(e) => set(i, { billing_cycle: e.target.value as Plan["billing_cycle"] })}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></NativeSelect></TableCell>
                {LIMITS.map((l) => <TableCell key={l}><Input aria-label={`${LIMIT_LABEL[l]} limit`} type="number" min={0} className="w-20" placeholder="∞" value={p.limits[l] ?? ""} onChange={(e) => set(i, { limits: { ...p.limits, [l]: e.target.value === "" ? null : Number(e.target.value) } })} /></TableCell>)}
                <TableCell><Switch checked={p.is_active} onCheckedChange={(v) => set(i, { is_active: v })} aria-label="Offered" /></TableCell>
                <TableCell><Button size="icon" variant="ghost" aria-label="Remove plan" onClick={() => setPlans((ps) => ps.filter((_, j) => j !== i))}><Trash2 /></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setPlans((ps) => [...ps, { code: `plan${ps.length + 1}`, name: "New plan", price_paise: 0, billing_cycle: "monthly", limits: {}, description: null, is_active: true }])}><Plus /> Add plan</Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending} data-testid="save-plans">Save plans</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function SubscriptionsPage() {
  const plans = useQuery({ queryKey: ["platform-plans"], queryFn: platformService.plans });
  const [filter, setFilter] = useState({ search: "", plan: "", status: "", over_limit: false });
  const subs = useQuery({ queryKey: ["platform-subs", filter], queryFn: () => platformService.subscriptions({ search: filter.search || undefined, plan: filter.plan || undefined, status: filter.status || undefined, over_limit: filter.over_limit || undefined }) });
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Subscriptions" description="Plans, limits and what each organization is on. No payment gateway is involved; record plan changes after you invoice and collect." />
      {plans.data ? <PlansEditor key={JSON.stringify(plans.data)} initial={plans.data} /> : <Skeleton className="h-48" />}
      <Card>
        <CardHeader><CardTitle className="text-base">Organizations</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input className="w-56" placeholder="Search name or slug" value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} />
            <NativeSelect aria-label="Plan" className="w-40" value={filter.plan} onChange={(e) => setFilter({ ...filter, plan: e.target.value })}><option value="">All plans</option><option value="none">No plan</option>{plans.data?.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}</NativeSelect>
            <NativeSelect aria-label="Status" className="w-40" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}><option value="">All statuses</option>{Object.entries(SUBSCRIPTION_STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect>
            <label className="flex items-center gap-2 text-sm"><Switch checked={filter.over_limit} onCheckedChange={(v) => setFilter({ ...filter, over_limit: v })} /> Over limit only</label>
          </div>
          {!subs.data ? <Skeleton className="h-48" /> : (
            <Table className="text-sm" data-testid="subscriptions-table">
              <TableHeader><TableRow><TableHead>Organization</TableHead><TableHead>Plan</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Price</TableHead><TableHead className="text-right">Professionals</TableHead><TableHead className="text-right">Appointments (month)</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {subs.data.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell><Link href={`/super-admin/organizations/${o.id}`} className="font-medium underline-offset-2 hover:underline">{o.name}</Link></TableCell>
                    <TableCell>{o.subscription?.plan_name ?? <span className="text-muted-foreground">No plan</span>}</TableCell>
                    <TableCell>{o.subscription ? <Badge variant={o.subscription.status === "active" ? "success" : o.subscription.status === "trial" ? "secondary" : "warning"}>{SUBSCRIPTION_STATUS_LABEL[o.subscription.status]}</Badge> : "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{o.subscription ? `${formatPaise(o.subscription.price_paise)}/${o.subscription.billing_cycle}` : "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{o.usage.professionals}{o.subscription?.limits.professionals != null ? ` / ${o.subscription.limits.professionals}` : ""}</TableCell>
                    <TableCell className="text-right tabular-nums">{o.usage.appointments_this_month}{o.subscription?.limits.appointments_per_month != null ? ` / ${o.subscription.limits.appointments_per_month}` : ""}</TableCell>
                    <TableCell>{o.over_limit.length ? <Badge variant="destructive">Over limit: {o.over_limit.map((k) => LIMIT_LABEL[k as keyof typeof LIMIT_LABEL]).join(", ")}</Badge> : null}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
