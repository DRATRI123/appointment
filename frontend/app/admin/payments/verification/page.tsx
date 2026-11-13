"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { paymentsService } from "@/services/payments";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PaymentsTable } from "@/components/payments/payments-table";
import { PaymentSheet } from "@/components/payments/payment-sheet";
import { PaymentStatsRow } from "@/components/payments/payment-stats";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function VerificationPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const [tab, setTab] = useState("submitted,under_review");
  const [selected, setSelected] = useState<string | null>(null);
  const queue = useQuery({ queryKey: ["payment-queue", orgId, tab], queryFn: () => paymentsService.queue({ status: tab, page_size: 100 }), enabled: !!orgId && hasPermission("payments:verify"), refetchInterval: 30_000 });
  if (!hasPermission("payments:verify")) return <Alert variant="destructive"><AlertDescription>Only staff with the payments:verify permission can approve or reject payments.</AlertDescription></Alert>;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Payment verification" description="Customers' UPI submissions, oldest first. Open each one, find the credit in your bank account, then approve or reject." />
      <PaymentStatsRow orgId={orgId} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList><TabsTrigger value="submitted,under_review">To verify</TabsTrigger><TabsTrigger value="verified">Verified</TabsTrigger><TabsTrigger value="rejected">Rejected</TabsTrigger></TabsList>
      </Tabs>
      {queue.isLoading ? <Skeleton className="h-64" /> : queue.data?.data.length === 0 ? (
        <EmptyState icon={ShieldCheck} title={tab.startsWith("submitted") ? "Nothing to verify" : "Nothing here yet"} body="New UPI submissions appear here automatically." />
      ) : <PaymentsTable rows={queue.data?.data ?? []} onOpen={setSelected} showSubmitted />}
      {selected ? <PaymentSheet id={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
