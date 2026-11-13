"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RotateCcw } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { refundsService } from "@/services/refunds";
import { RefundStatusBadge } from "@/components/refunds/refund-status-badge";
import { RefundSheet, REFUND_QUERY_KEYS } from "@/components/refunds/refund-sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { MoneyInput } from "@/components/forms/money-input";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import type { RefundSummary } from "@/types/refund";

/** Refund position and history of one payment, with a request form for staff holding refunds:request. */
export function PaymentRefunds({ summary }: { summary: RefundSummary }) {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState<number | null>(summary.suggested_paise || summary.refundable_paise);
  const [reason, setReason] = useState("");
  const [destination, setDestination] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const request = useMutation({
    mutationFn: () => refundsService.request({ payment_id: summary.payment_id, amount_paise: amount ?? undefined, reason, destination: destination || undefined }),
    onSuccess: () => { toast.success("Refund requested. An approver will review it."); setOpen(false); setReason(""); REFUND_QUERY_KEYS.forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const canRequest = hasPermission("refunds:request") && summary.refundable_paise > 0;
  return (
    <div className="space-y-3 rounded-xl border p-4" data-testid="payment-refunds">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium"><RotateCcw className="size-4" /> Refunds</p>
        {canRequest && !open ? <Button size="sm" variant="outline" onClick={() => setOpen(true)}>Request refund</Button> : null}
      </div>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div><dt className="text-muted-foreground">Refunded</dt><dd className="text-sm font-semibold">{formatPaise(summary.refunded_paise)}</dd></div>
        <div><dt className="text-muted-foreground">In progress</dt><dd className="text-sm font-semibold">{formatPaise(summary.pending_paise)}</dd></div>
        <div><dt className="text-muted-foreground">Still refundable</dt><dd className="text-sm font-semibold">{formatPaise(summary.refundable_paise)}</dd></div>
      </dl>
      {open ? (
        <div className="space-y-3 border-t pt-3">
          {summary.suggestion_reason ? <p className="text-xs text-muted-foreground">Suggested {formatPaise(summary.suggested_paise)}: {summary.suggestion_reason}</p> : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Amount" htmlFor="rq_amount" hint={`Up to ${formatPaise(summary.refundable_paise)}`}><MoneyInput id="rq_amount" valuePaise={amount} onChange={setAmount} /></Field>
            <Field label="Send to (customer's UPI ID / account)" htmlFor="rq_dest" hint="Defaults to the UPI ID the customer paid from"><Input id="rq_dest" value={destination} onChange={(e) => setDestination(e.target.value)} /></Field>
          </div>
          <Field label="Reason" htmlFor="rq_reason"><Textarea id="rq_reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => request.mutate()} disabled={reason.trim().length < 3 || !amount || amount > summary.refundable_paise || request.isPending} data-testid="submit-refund-request">Submit request</Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </div>
      ) : null}
      {summary.refunds.length ? (
        <ul className="space-y-1.5 border-t pt-3">
          {summary.refunds.map((r) => (
            <li key={r.id}><button type="button" className="flex w-full flex-wrap items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted/60" onClick={() => setSelected(r.id)}>
              <span className="font-medium">{formatPaise(r.amount_paise)}</span><RefundStatusBadge status={r.status} /><span className="text-xs text-muted-foreground">{formatDateTime(r.requested_at)} · {r.reason}</span>
            </button></li>
          ))}
        </ul>
      ) : null}
      {selected ? <RefundSheet id={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
