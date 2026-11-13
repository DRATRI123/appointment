"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CreditCard } from "lucide-react";
import { paymentsService } from "@/services/payments";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PaymentStatusBadge } from "@/components/payments/payment-status-badge";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { METHOD_LABEL } from "@/types/payment";

export default function CustomerPaymentsPage() {
  const payments = useQuery({ queryKey: ["my-payments"], queryFn: paymentsService.mine });
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Payments" description="Every payment you made or still owe, with the clinic's verification status." />
      {payments.isLoading ? <Skeleton className="h-48" /> : payments.data?.length === 0 ? <EmptyState icon={CreditCard} title="No payments yet" body="Payments appear here when a booking asks for an advance." /> : (
        <div className="space-y-2">
          {payments.data?.map((p) => (
            <Card key={p.id} className="py-4" data-testid="my-payment">
              <CardContent className="flex flex-wrap items-center gap-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{formatPaise(p.verified_amount_paise ?? p.amount_paise)} · {p.organization_name}</p>
                  <p className="text-sm text-muted-foreground">{p.service_name} · {METHOD_LABEL[p.method]} · <span className="font-mono text-xs">{p.reference}</span></p>
                  <p className="text-xs text-muted-foreground">{p.verified_at ? `Verified ${formatDateTime(p.verified_at)}` : p.submitted_at ? `Submitted ${formatDateTime(p.submitted_at)}` : `Requested ${formatDateTime(p.created_at)}`}{p.latest_utr ? ` · UTR ${p.latest_utr}` : ""}{p.rejection_reason ? ` · ${p.rejection_reason}` : ""}</p>
                </div>
                <PaymentStatusBadge status={p.status} />
                {p.appointment_reference && p.organization_slug && ["awaiting_payment", "rejected"].includes(p.status) ? <Link className="text-sm font-medium text-primary underline" href={`/o/${p.organization_slug}/appointments/${p.appointment_reference}`}>Pay now</Link> : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
