"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { refundsService } from "@/services/refunds";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { RefundSheet } from "@/components/refunds/refund-sheet";
import { RefundStatusBadge } from "@/components/refunds/refund-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";

const TABS: [string, string][] = [["requested", "To approve"], ["approved", "To send"], ["processed", "Refunded"], ["rejected,cancelled", "Closed"], ["", "All"]];

export default function RefundsPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const [status, setStatus] = useState("requested");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const canView = hasPermission("refunds:request") || hasPermission("refunds:approve");
  const stats = useQuery({ queryKey: ["refund-stats", orgId], queryFn: refundsService.stats, enabled: !!orgId && canView });
  const refunds = useQuery({ queryKey: ["refunds", orgId, status, search, page], queryFn: () => refundsService.list({ status: status || undefined, search: search || undefined, page, page_size: 25 }), enabled: !!orgId && canView });
  const pages = refunds.data ? Math.max(1, Math.ceil(refunds.data.meta.total / refunds.data.meta.page_size)) : 1;
  const s = stats.data;
  const cards: [string, React.ReactNode][] = [
    ["Waiting for approval", s ? s.requested : "—"],
    ["Approved, not yet sent", s ? s.approved : "—"],
    ["Amount in progress", s ? formatPaise(s.pending_amount_paise) : "—"],
    ["Refunded this month", s ? `${s.processed_this_month} · ${formatPaise(s.processed_amount_this_month_paise)}` : "—"],
  ];
  if (!canView) return <EmptyState icon={RotateCcw} title="No access" body="You need refund permissions to see this page." />;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Refunds" description="Request, approve and record refunds of verified payments. Refunds are sent from your own bank or UPI app; a refund shows as refunded only after staff record its reference." />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([label, value]) => <Card key={label} className="gap-1 py-4"><CardHeader><CardDescription>{label}</CardDescription></CardHeader><CardContent className="text-xl font-semibold">{value}</CardContent></Card>)}
      </div>
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-full overflow-x-auto">
          <Tabs value={status} onValueChange={(v) => { setPage(1); setStatus(v); }}>
            <TabsList>{TABS.map(([v, label]) => <TabsTrigger key={label} value={v}>{label}</TabsTrigger>)}</TabsList>
          </Tabs>
        </div>
        <Input className="lg:w-80" placeholder="Search refund, payment, UTR, customer" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
      </div>
      {refunds.isLoading ? <Skeleton className="h-64" /> : refunds.data?.data.length === 0 ? (
        <EmptyState icon={RotateCcw} title="Nothing here" body="Refund requests appear here when staff request one from a payment, or when a paid appointment is cancelled within the refund window." />
      ) : (
        <>
          <Table>
              <TableHeader><TableRow><TableHead>Requested</TableHead><TableHead>Customer</TableHead><TableHead>Amount</TableHead><TableHead>Reason</TableHead><TableHead>Payment</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
              <TableBody>
                {refunds.data?.data.map((r) => (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => setSelected(r.id)} data-testid="refund-row">
                    <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.requested_at)}<span className="block text-xs">{r.requested_by_name}</span></TableCell>
                    <TableCell>{r.customer_name}<span className="block text-xs text-muted-foreground">{r.customer_mobile}</span></TableCell>
                    <TableCell className="font-medium">{formatPaise(r.amount_paise)}</TableCell>
                    <TableCell className="max-w-72 truncate">{r.reason}</TableCell>
                    <TableCell className="font-mono text-xs">{r.payment_reference}{r.refund_reference ? <span className="block text-muted-foreground">sent: {r.refund_reference}</span> : null}</TableCell>
                    <TableCell><RefundStatusBadge status={r.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
          </Table>
          <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{refunds.data?.meta.total} refunds</span><div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div></div>
        </>
      )}
      {selected ? <RefundSheet id={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
