"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, Landmark } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { paymentsService } from "@/services/payments";
import { PaymentStatusBadge } from "@/components/payments/payment-status-badge";
import { PrivateImage } from "@/components/payments/private-image";
import { UpiCheckout } from "@/components/payments/upi-checkout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Field } from "@/components/forms/field";
import { MoneyInput } from "@/components/forms/money-input";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { METHOD_LABEL } from "@/types/payment";

export function PaymentSheet({ id, onClose }: { id: string; onClose: () => void }) {
  const { hasPermission, currentOrganizationId } = useAuth();
  const canVerify = hasPermission("payments:verify");
  const queryClient = useQueryClient();
  const payment = useQuery({ queryKey: ["payment", id], queryFn: () => paymentsService.get(id) });
  const [credit, setCredit] = useState(false);
  const [amount, setAmount] = useState<number | null>(null);
  const [mismatch, setMismatch] = useState("");
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [showQr, setShowQr] = useState(false);
  const checkout = useQuery({ queryKey: ["payment-checkout", id], queryFn: () => paymentsService.checkout(id), enabled: showQr });
  const refresh = () => ["payment", "payments", "payment-queue", "payment-stats", "appointments", "appointment", "calendar"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));
  const done = (msg: string) => () => { toast.success(msg); setNotes(""); setReason(""); refresh(); };
  const review = useMutation({ mutationFn: () => paymentsService.review(id), onSuccess: done("Marked as under review"), onError: (e) => toast.error(errorMessage(e)) });
  const verify = useMutation({ mutationFn: () => paymentsService.verify(id, { bank_credit_confirmed: credit, verified_amount_paise: amount ?? p!.amount_paise, amount_mismatch_reason: mismatch || undefined, notes: notes || undefined }), onSuccess: done("Payment verified. The appointment is confirmed."), onError: (e) => toast.error(errorMessage(e)) });
  const reject = useMutation({ mutationFn: () => paymentsService.reject(id, { reason, notes: notes || undefined }), onSuccess: done("Payment rejected. The customer can submit again."), onError: (e) => toast.error(errorMessage(e)) });
  const note = useMutation({ mutationFn: () => paymentsService.note(id, notes), onSuccess: done("Note added"), onError: (e) => toast.error(errorMessage(e)) });
  const p = payment.data;
  const inReview = p && ["submitted", "under_review"].includes(p.status);
  const latest = p?.submissions.find((s) => !s.is_superseded) ?? p?.submissions[0];
  const verifiedAmount = amount ?? p?.amount_paise ?? 0;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-2xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">{p ? formatPaise(p.amount_paise) : "Payment"} {p ? <PaymentStatusBadge status={p.status} /> : null}</SheetTitle>
          <SheetDescription>{p ? `${p.reference} · ${METHOD_LABEL[p.method]} · ${p.kind}` : ""}</SheetDescription>
        </SheetHeader>
        {!p ? <Skeleton className="h-64" /> : (
          <div className="space-y-6 text-sm">
            {p.duplicate_utr_flag ? <Alert variant="destructive"><AlertTriangle /><AlertDescription>The same UTR was also submitted for another payment. Check the history below before approving.</AlertDescription></Alert> : null}
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              <div><dt className="text-muted-foreground">Customer</dt><dd className="font-medium">{p.customer_name} <span className="text-muted-foreground">{p.customer_mobile}</span></dd></div>
              <div><dt className="text-muted-foreground">Appointment</dt><dd>{p.service_name} · {p.appointment_start_at ? formatDateTime(p.appointment_start_at, p.appointment_timezone) : "—"}<span className="block font-mono text-xs text-muted-foreground">{p.appointment_reference} · {p.appointment_status?.replace(/_/g, " ")}</span></dd></div>
              <div><dt className="text-muted-foreground">Collect into</dt><dd>{p.upi_account_name ?? "—"} <span className="font-mono text-xs text-muted-foreground">{p.upi_id}</span></dd></div>
              <div><dt className="text-muted-foreground">Expected amount</dt><dd className="text-base font-semibold">{formatPaise(p.amount_paise)}</dd></div>
              {p.verified_amount_paise !== null ? <div><dt className="text-muted-foreground">Verified amount</dt><dd className="font-semibold">{formatPaise(p.verified_amount_paise)}</dd></div> : null}
              {p.rejection_reason ? <div className="sm:col-span-2"><dt className="text-muted-foreground">Rejection reason</dt><dd>{p.rejection_reason}</dd></div> : null}
            </dl>

            {latest ? (
              <div className="space-y-3 rounded-xl border p-4" data-testid="submission">
                <p className="font-medium">Customer submission</p>
                <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  <div><dt className="text-muted-foreground">UTR</dt><dd className="font-mono text-base">{latest.utr}</dd></div>
                  <div><dt className="text-muted-foreground">Submitted</dt><dd>{formatDateTime(latest.created_at)}</dd></div>
                  {latest.paid_at ? <div><dt className="text-muted-foreground">Paid at (customer)</dt><dd>{formatDateTime(latest.paid_at)}</dd></div> : null}
                  {latest.transaction_reference ? <div><dt className="text-muted-foreground">App transaction ID</dt><dd className="font-mono">{latest.transaction_reference}</dd></div> : null}
                  {latest.notes ? <div className="sm:col-span-2"><dt className="text-muted-foreground">Note</dt><dd>{latest.notes}</dd></div> : null}
                </dl>
                {latest.has_screenshot ? <PrivateImage url={paymentsService.screenshotUrl(p.id, latest.id)} organizationId={currentOrganizationId} alt="Payment screenshot" /> : <p className="text-muted-foreground">No screenshot attached.</p>}
                <p className="text-xs text-muted-foreground">A screenshot can be edited. Approve only after you see this credit in the bank account or statement.</p>
              </div>
            ) : null}

            {canVerify && inReview ? (
              <div className="space-y-4 rounded-xl border border-primary/30 p-4" data-testid="verify-panel">
                <p className="flex items-center gap-2 font-medium"><Landmark className="size-4" /> Verify against the bank</p>
                {p.status === "submitted" ? <Button size="sm" variant="outline" onClick={() => review.mutate()} disabled={review.isPending}>I&apos;m checking this one</Button> : null}
                <label className="flex items-start gap-2"><Checkbox checked={credit} onCheckedChange={(v) => setCredit(v === true)} data-testid="bank-credit" /> <span>I confirmed this UTR and amount in the bank account or statement.</span></label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Amount credited" htmlFor="v_amount"><MoneyInput id="v_amount" valuePaise={verifiedAmount} onChange={(v) => setAmount(v ?? 0)} /></Field>
                  {verifiedAmount !== p.amount_paise ? <Field label="Why is the amount different?" htmlFor="v_mismatch"><Input id="v_mismatch" value={mismatch} onChange={(e) => setMismatch(e.target.value)} /></Field> : null}
                </div>
                <Field label="Internal note" htmlFor="v_notes"><Textarea id="v_notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => verify.mutate()} disabled={!credit || verify.isPending} data-testid="approve-payment">Approve payment</Button>
                  <Input className="w-64" placeholder="Rejection reason" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="reject-reason" />
                  <Button variant="destructive" onClick={() => reject.mutate()} disabled={reason.trim().length < 3 || reject.isPending}>Reject</Button>
                  <Button variant="ghost" onClick={() => note.mutate()} disabled={!notes.trim() || note.isPending}>Add note only</Button>
                </div>
              </div>
            ) : null}

            {p.method === "upi_qr" && ["awaiting_payment", "rejected"].includes(p.status) ? (
              <div className="space-y-3">
                <Button size="sm" variant="outline" onClick={() => setShowQr((v) => !v)}>{showQr ? "Hide QR" : "Show QR to the customer"}</Button>
                {showQr && checkout.data ? <UpiCheckout checkout={checkout.data} compact /> : null}
              </div>
            ) : null}

            <div>
              <p className="mb-2 font-medium">History</p>
              <ol className="space-y-1.5 text-xs" data-testid="payment-history">
                {p.logs.map((l, i) => <li key={i} className="rounded-md bg-muted/40 px-2 py-1.5"><span className="font-medium">{l.action.replace(/_/g, " ")}</span>{l.from_status && l.from_status !== l.to_status ? ` · ${l.from_status} → ${l.to_status}` : ""} · {formatDateTime(l.created_at)}{l.actor_name ? ` · ${l.actor_name}` : ""}{l.bank_credit_confirmed ? " · bank credit confirmed" : ""}{l.reason ? <span className="block text-muted-foreground">{l.reason}</span> : null}{l.details?.other_payment ? <span className="block text-destructive">Also used on {String(l.details.other_payment)}</span> : null}</li>)}
              </ol>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
