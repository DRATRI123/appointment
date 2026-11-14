"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CreditCard, ShieldCheck } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { paymentsService } from "@/services/payments";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { PaymentsTable } from "@/components/payments/payments-table";
import { PaymentSheet } from "@/components/payments/payment-sheet";
import { PaymentStatsRow } from "@/components/payments/payment-stats";
import { PAYMENT_STATUS_LABEL, METHOD_LABEL } from "@/types/payment";

export default function PaymentsPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const payments = useQuery({ queryKey: ["payments", orgId, status, method, search, page], queryFn: () => paymentsService.list({ status: status || undefined, method: method || undefined, search: search || undefined, page, page_size: 25 }), enabled: !!orgId });
  const pages = payments.data ? Math.max(1, Math.ceil(payments.data.meta.total / payments.data.meta.page_size)) : 1;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Payments" description="Every payment request, UPI submission, cash collection and bank transfer, with its full verification trail." actions={hasPermission("payments:verify") ? <Button asChild><Link href="/admin/payments/verification"><ShieldCheck /> Verification queue</Link></Button> : null} />
      <PaymentStatsRow orgId={orgId} />
      <div className="grid gap-2 sm:grid-cols-3">
        <Input placeholder="Search reference, UTR, customer, mobile" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
        <NativeSelect aria-label="Status" value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }}><option value="">All statuses</option>{Object.entries(PAYMENT_STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect>
        <NativeSelect aria-label="Method" value={method} onChange={(e) => { setPage(1); setMethod(e.target.value); }}><option value="">All methods</option>{(["upi_qr", "cash", "bank_transfer"] as const).map((k) => <option key={k} value={k}>{METHOD_LABEL[k]}</option>)}</NativeSelect>
      </div>
      {payments.isLoading ? <Skeleton className="h-64" /> : payments.data?.data.length === 0 ? (
        <EmptyState icon={CreditCard} title="No payments match" body="Payment requests appear here as soon as a booking needs an advance." />
      ) : (
        <>
          <PaymentsTable rows={payments.data?.data ?? []} onOpen={setSelected} />
          <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{payments.data?.meta.total} payments</span><div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div></div>
        </>
      )}
      {selected ? <PaymentSheet id={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
