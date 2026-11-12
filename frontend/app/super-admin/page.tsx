"use client";

import { useQuery } from "@tanstack/react-query";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function SuperAdminOverview() {
  const stats = useQuery({ queryKey: ["platform-stats"], queryFn: platformService.stats });
  const items = [
    ["Organizations", stats.data?.organizations_total],
    ["Active organizations", stats.data?.organizations_active],
    ["Users", stats.data?.users_total],
    ["Audit events (24h)", stats.data?.audit_events_24h],
  ] as const;
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Platform overview" description="Tenants, users and activity across the whole platform." />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map(([label, value]) => (
          <Card key={label} className="gap-1 py-4">
            <CardHeader><CardDescription>{label}</CardDescription></CardHeader>
            <CardContent className="text-2xl font-semibold">{stats.isLoading ? <Skeleton className="h-7 w-16" /> : value}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
