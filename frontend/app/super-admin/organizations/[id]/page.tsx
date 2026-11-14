"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { SubscriptionForm } from "@/components/platform/subscription-form";
import { UsageMeters } from "@/components/platform/usage-meters";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { SUBSCRIPTION_STATUS_LABEL } from "@/types/platform";

export default function OrganizationDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const org = useQuery({ queryKey: ["platform-org", id], queryFn: () => platformService.overview(id) });
  const plans = useQuery({ queryKey: ["platform-plans"], queryFn: platformService.plans });
  const history = useQuery({ queryKey: ["platform-history", id], queryFn: () => platformService.history(id) });
  const o = org.data;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <Link href="/super-admin/organizations" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Organizations</Link>
      {!o ? <Skeleton className="h-96" /> : (
        <>
          <PageHeader title={o.name} description={`/${o.slug} · ${o.timezone} · created ${formatDateTime(o.created_at)}`} actions={<Badge variant={o.status === "active" ? "success" : "warning"}>{o.status}</Badge>} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card><CardHeader><CardTitle className="text-base">Contact</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">
              <p><span className="text-muted-foreground">Owner:</span> {o.owner_name ?? "—"} <span className="text-muted-foreground">{o.owner_contact}</span></p>
              <p><span className="text-muted-foreground">Email:</span> {o.email ?? "—"}</p><p><span className="text-muted-foreground">Phone:</span> {o.phone ?? "—"}</p>
              <p><span className="text-muted-foreground">Customers:</span> {o.usage.customers} · <span className="text-muted-foreground">appointments (30 days):</span> {o.usage.appointments_30d}</p>
              <p><span className="text-muted-foreground">Verified receipts (30 days):</span> {formatPaise(o.usage.verified_receipts_30d_paise)}</p>
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="text-base">Usage</CardTitle><CardDescription>{o.subscription ? `${o.subscription.plan_name} · ${SUBSCRIPTION_STATUS_LABEL[o.subscription.status]}` : "No plan: unlimited"}</CardDescription></CardHeader><CardContent><UsageMeters org={o} /></CardContent></Card>
            <Card><CardHeader><CardTitle className="text-base">Recent activity</CardTitle></CardHeader><CardContent>
              <ol className="max-h-64 space-y-1 overflow-y-auto text-xs">{o.recent_activity.map((a, i) => <li key={i}><span className="font-medium">{a.action}</span> · {a.actor ?? "system"} · <span className="text-muted-foreground">{formatDateTime(a.at)}</span></li>)}</ol>
            </CardContent></Card>
          </div>
          <Card>
            <CardHeader><CardTitle className="text-base">Subscription</CardTitle><CardDescription>Plans are invoiced and collected outside the platform. Record each change here; limits apply immediately.</CardDescription></CardHeader>
            <CardContent className="space-y-6">
              {plans.data ? <SubscriptionForm key={o.subscription?.id ?? "none"} org={o} plans={plans.data} /> : <Skeleton className="h-40" />}
              {history.data?.length ? (
                <div><p className="mb-2 text-sm font-medium">History</p>
                  <ol className="space-y-1 text-xs" data-testid="subscription-history">{history.data.map((h) => <li key={h.id}>{formatDateTime(h.created_at)} · <span className="font-medium">{h.plan_name}</span> · {SUBSCRIPTION_STATUS_LABEL[h.status]} · {formatPaise(h.price_paise)}/{h.billing_cycle}{h.notes ? ` · ${h.notes}` : ""}</li>)}</ol>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
