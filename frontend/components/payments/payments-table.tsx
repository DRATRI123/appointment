"use client";

import { AlertTriangle } from "lucide-react";
import { PaymentStatusBadge } from "@/components/payments/payment-status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { METHOD_LABEL, type Payment } from "@/types/payment";

export function PaymentsTable({ rows, onOpen, showSubmitted = false }: { rows: Payment[]; onOpen: (id: string) => void; showSubmitted?: boolean }) {
  return (
    <Table>
      <TableHeader><TableRow><TableHead>{showSubmitted ? "Submitted" : "Created"}</TableHead><TableHead>Customer</TableHead><TableHead>Amount</TableHead><TableHead>Method</TableHead><TableHead>UTR</TableHead><TableHead>Appointment</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
      <TableBody>
        {rows.map((p) => (
          <TableRow key={p.id} className="cursor-pointer" onClick={() => onOpen(p.id)} data-testid="payment-row">
            <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(showSubmitted ? p.submitted_at ?? p.created_at : p.created_at)}</TableCell>
            <TableCell>{p.customer_name}<span className="block text-xs text-muted-foreground">{p.customer_mobile}</span></TableCell>
            <TableCell className="font-medium">{formatPaise(p.amount_paise)}{p.verified_amount_paise !== null && p.verified_amount_paise !== p.amount_paise ? <span className="block text-xs text-muted-foreground">verified {formatPaise(p.verified_amount_paise)}</span> : null}</TableCell>
            <TableCell>{METHOD_LABEL[p.method]}<span className="block text-xs text-muted-foreground">{p.kind}</span></TableCell>
            <TableCell className="font-mono text-xs">{p.latest_utr ?? "—"}{p.duplicate_utr_flag ? <span className="ml-1 inline-flex items-center gap-0.5 text-destructive"><AlertTriangle className="size-3" />dup</span> : null}</TableCell>
            <TableCell className="text-xs">{p.service_name}<span className="block text-muted-foreground">{p.appointment_start_at ? formatDateTime(p.appointment_start_at, p.appointment_timezone) : ""}</span></TableCell>
            <TableCell><PaymentStatusBadge status={p.status} /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
