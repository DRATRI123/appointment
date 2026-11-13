"use client";

import { useQuery } from "@tanstack/react-query";
import { paymentsService } from "@/services/payments";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { formatPaise } from "@/lib/utils";

export function PaymentStatsRow({ orgId }: { orgId: string | null }) {
  const stats = useQuery({ queryKey: ["payment-stats", orgId], queryFn: paymentsService.stats, enabled: !!orgId, refetchInterval: 60_000 });
  const s = stats.data;
  const items: [string, React.ReactNode][] = [
    ["Waiting for verification", s ? s.submitted + s.under_review : "—"],
    ["Amount to verify", s ? formatPaise(s.pending_amount_paise) : "—"],
    ["Verified today", s ? `${s.verified_today} · ${formatPaise(s.verified_amount_today_paise)}` : "—"],
    ["Awaiting customer payment", s ? s.awaiting_payment : "—"],
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {items.map(([label, value]) => <Card key={label} className="gap-1 py-4"><CardHeader><CardDescription>{label}</CardDescription></CardHeader><CardContent className="text-xl font-semibold">{value}</CardContent></Card>)}
    </div>
  );
}
