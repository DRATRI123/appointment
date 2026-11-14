"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";
import { developersService } from "@/services/developers";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { StatTile } from "@/components/analytics/stat-tile";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { compactNumber } from "@/lib/numbers";

export default function ApiUsagePage() {
  const [days, setDays] = useState(30);
  const usage = useQuery({ queryKey: ["platform-api-usage", days], queryFn: () => developersService.platformUsage(days), placeholderData: keepPreviousData });
  const rows = usage.data ?? [];
  const sum = (k: "requests" | "errors" | "rate_limited" | "deliveries_ok" | "deliveries_failed" | "active_keys") => rows.reduce((a, r) => a + r[k], 0);
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Usage & API" description="API requests and webhook delivery health per organization." />
      <NativeSelect aria-label="Period" className="w-40" value={days} onChange={(e) => setDays(Number(e.target.value))}>{[1, 7, 30, 90].map((d) => <option key={d} value={d}>Last {d} day{d > 1 ? "s" : ""}</option>)}</NativeSelect>
      {usage.isLoading ? <Skeleton className="h-64" /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile hero label="API requests" value={compactNumber(sum("requests"))} hint={`${compactNumber(sum("errors"))} errors · ${compactNumber(sum("rate_limited"))} rate-limited`} />
            <StatTile label="Active API keys" value={compactNumber(sum("active_keys"))} />
            <StatTile label="Webhooks delivered" value={compactNumber(sum("deliveries_ok"))} hint={`${compactNumber(sum("deliveries_failed"))} failed or retrying`} />
          </div>
          {rows.length === 0 ? <EmptyState icon={Gauge} title="No API activity" body="Organizations have not created API keys or webhooks yet." /> : (
            <Table className="text-sm" data-testid="usage-table">
              <TableHeader><TableRow><TableHead>Organization</TableHead><TableHead className="text-right">Keys</TableHead><TableHead className="text-right">Requests</TableHead><TableHead className="text-right">Errors</TableHead><TableHead className="text-right">Rate-limited</TableHead><TableHead className="text-right">Endpoints</TableHead><TableHead className="text-right">Delivered</TableHead><TableHead className="text-right">Failed</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.organization_id}>
                    <TableCell><Link className="underline-offset-2 hover:underline" href={`/super-admin/organizations/${r.organization_id}`}>{r.organization_name}</Link></TableCell>
                    <TableCell className="text-right tabular-nums">{r.active_keys}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.requests}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.errors}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.rate_limited}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.endpoints}{r.endpoints_disabled ? <span className="text-[var(--viz-down-bad)]"> ({r.endpoints_disabled} off)</span> : null}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.deliveries_ok}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.deliveries_failed}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}
