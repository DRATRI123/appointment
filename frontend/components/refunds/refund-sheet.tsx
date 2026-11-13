"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Info } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { refundsService } from "@/services/refunds";
import { RefundStatusBadge } from "@/components/refunds/refund-status-badge";
import { PrivateImage } from "@/components/payments/private-image";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { REFUND_METHOD_LABEL, type Refund, type RefundMethod } from "@/types/refund";

export const REFUND_QUERY_KEYS = ["refunds", "refund", "refund-stats", "payment", "payments", "payment-stats", "appointment", "appointments"];

export function RefundSheet({ id, onClose }: { id: string; onClose: () => void }) {
  const { hasPermission, currentOrganizationId } = useAuth();
  const canApprove = hasPermission("refunds:approve");
  const queryClient = useQueryClient();
  const refund = useQuery({ queryKey: ["refund", id], queryFn: () => refundsService.get(id) });
  const r = refund.data;
  const refresh = () => REFUND_QUERY_KEYS.forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));
  const ok = (msg: string) => () => { toast.success(msg); refresh(); };
  const [rejectReason, setRejectReason] = useState("");
  const approve = useMutation({ mutationFn: () => refundsService.approve(id), onSuccess: ok("Refund approved. Send it from your bank or UPI app, then record it here."), onError: (e) => toast.error(errorMessage(e)) });
  const reject = useMutation({ mutationFn: () => refundsService.reject(id, rejectReason), onSuccess: ok("Refund rejected"), onError: (e) => toast.error(errorMessage(e)) });
  const withdraw = useMutation({ mutationFn: () => refundsService.cancel(id), onSuccess: ok("Refund request withdrawn"), onError: (e) => toast.error(errorMessage(e)) });
  const canWithdraw = r && ["requested", "approved"].includes(r.status) && (canApprove || hasPermission("refunds:request"));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">{r ? formatPaise(r.amount_paise) : "Refund"} {r ? <RefundStatusBadge status={r.status} /> : null}</SheetTitle>
          <SheetDescription>{r ? `${r.reference} · for payment ${r.payment_reference}` : ""}</SheetDescription>
        </SheetHeader>
        {!r ? <Skeleton className="h-64" /> : (
          <div className="space-y-6 text-sm">
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              <div><dt className="text-muted-foreground">Customer</dt><dd className="font-medium">{r.customer_name} <span className="text-muted-foreground">{r.customer_mobile}</span></dd></div>
              <div><dt className="text-muted-foreground">Appointment</dt><dd className="font-mono text-xs">{r.appointment_reference ?? "—"}<span className="block font-sans text-muted-foreground">{r.appointment_status?.replace(/_/g, " ")}</span></dd></div>
              <div><dt className="text-muted-foreground">Payment verified</dt><dd>{r.payment_verified_amount_paise !== null ? formatPaise(r.payment_verified_amount_paise) : "—"}</dd></div>
              <div><dt className="text-muted-foreground">Send to</dt><dd className="font-mono text-xs">{r.destination ?? "—"}</dd></div>
              <div className="sm:col-span-2"><dt className="text-muted-foreground">Reason</dt><dd>{r.reason}</dd></div>
              {r.rejection_reason ? <div className="sm:col-span-2"><dt className="text-muted-foreground">Rejected because</dt><dd>{r.rejection_reason}</dd></div> : null}
              {r.status === "processed" ? (
                <>
                  <div><dt className="text-muted-foreground">Sent via</dt><dd>{r.refund_method ? REFUND_METHOD_LABEL[r.refund_method] : "—"}</dd></div>
                  <div><dt className="text-muted-foreground">Refund reference</dt><dd className="font-mono">{r.refund_reference ?? "—"}</dd></div>
                </>
              ) : null}
              {r.notes ? <div className="sm:col-span-2"><dt className="text-muted-foreground">Notes</dt><dd className="whitespace-pre-line">{r.notes}</dd></div> : null}
            </dl>

            <ol className="space-y-1 text-xs text-muted-foreground" data-testid="refund-timeline">
              <li>Requested {formatDateTime(r.requested_at)} by {r.requested_by_name ?? "—"}</li>
              {r.approved_at ? <li>Approved {formatDateTime(r.approved_at)} by {r.approved_by_name}</li> : null}
              {r.processed_at ? <li>Refund sent {formatDateTime(r.processed_at)}, recorded by {r.processed_by_name}</li> : null}
              {r.rejected_at ? <li>Rejected {formatDateTime(r.rejected_at)}</li> : null}
            </ol>

            {r.status === "requested" && canApprove ? (
              <div className="space-y-3 rounded-xl border p-4">
                <p className="font-medium">Decision</p>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => approve.mutate()} disabled={approve.isPending} data-testid="approve-refund">Approve refund</Button>
                  <Input className="w-full sm:w-60" placeholder="Rejection reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                  <Button variant="destructive" onClick={() => reject.mutate()} disabled={rejectReason.trim().length < 3 || reject.isPending}>Reject</Button>
                </div>
              </div>
            ) : null}

            {r.status === "approved" && canApprove ? <ProcessForm refund={r} onDone={refresh} /> : null}
            {r.status === "approved" && !canApprove ? <Alert><Info /><AlertDescription>Approved. An accountant records the refund once it has been sent.</AlertDescription></Alert> : null}

            {r.status === "processed" ? (
              <div className="space-y-2">
                <p className="font-medium">Proof</p>
                {r.has_proof ? <PrivateImage url={refundsService.proofUrl(r.id)} organizationId={currentOrganizationId} alt="Refund proof" /> : <p className="text-muted-foreground">No proof attached.</p>}
                {canApprove && !r.has_proof ? <ProofUpload id={r.id} onDone={refresh} /> : null}
              </div>
            ) : null}

            {canWithdraw ? (
              <Button variant="ghost" size="sm" onClick={() => withdraw.mutate()} disabled={withdraw.isPending}>Withdraw request</Button>
            ) : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function ProcessForm({ refund, onDone }: { refund: Refund; onDone: () => void }) {
  const [method, setMethod] = useState<RefundMethod>(refund.refund_method ?? "upi");
  const [reference, setReference] = useState("");
  const [destination, setDestination] = useState(refund.destination ?? "");
  const [sentAt, setSentAt] = useState("");
  const [notes, setNotes] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [proof, setProof] = useState<File | null>(null);
  const process = useMutation({
    mutationFn: async () => {
      const done = await refundsService.process(refund.id, {
        refund_method: method, refund_reference: reference || undefined, destination: destination || undefined,
        processed_at: sentAt ? new Date(sentAt).toISOString() : undefined, money_sent_confirmed: confirmed, notes: notes || undefined,
      });
      if (proof) await refundsService.uploadProof(refund.id, proof);
      return done;
    },
    onSuccess: () => { toast.success("Refund recorded as sent"); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const needsRef = method !== "cash";
  return (
    <div className="space-y-4 rounded-xl border border-primary/30 p-4" data-testid="process-refund">
      <div>
        <p className="font-medium">Record the refund you sent</p>
        <p className="text-xs text-muted-foreground">This system does not move money. Send {formatPaise(refund.amount_paise)} from your bank or UPI app first, then record the reference here.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Sent via" htmlFor="rf_method"><NativeSelect id="rf_method" value={method} onChange={(e) => setMethod(e.target.value as RefundMethod)}>{(Object.keys(REFUND_METHOD_LABEL) as RefundMethod[]).map((m) => <option key={m} value={m}>{REFUND_METHOD_LABEL[m]}</option>)}</NativeSelect></Field>
        {needsRef ? <Field label="Refund UTR / bank reference" htmlFor="rf_ref"><Input id="rf_ref" value={reference} onChange={(e) => setReference(e.target.value)} className="font-mono" /></Field> : null}
        <Field label="Sent to (UPI ID / account)" htmlFor="rf_dest"><Input id="rf_dest" value={destination} onChange={(e) => setDestination(e.target.value)} /></Field>
        <Field label="Sent on" htmlFor="rf_when" hint="Leave empty for now"><Input id="rf_when" type="datetime-local" value={sentAt} onChange={(e) => setSentAt(e.target.value)} /></Field>
      </div>
      <Field label={method === "cash" ? "Who handed over the cash?" : "Note"} htmlFor="rf_notes"><Textarea id="rf_notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <Field label="Proof (screenshot or PDF, optional)" htmlFor="rf_proof"><Input id="rf_proof" type="file" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={(e) => setProof(e.target.files?.[0] ?? null)} /></Field>
      <label className="flex items-start gap-2"><Checkbox checked={confirmed} onCheckedChange={(v) => setConfirmed(v === true)} data-testid="refund-sent" /> <span>I confirm this refund has been sent to the customer.</span></label>
      <Button onClick={() => process.mutate()} disabled={!confirmed || (needsRef ? !reference.trim() : !notes.trim()) || process.isPending} data-testid="mark-refunded">Mark as refunded</Button>
    </div>
  );
}

function ProofUpload({ id, onDone }: { id: string; onDone: () => void }) {
  const upload = useMutation({ mutationFn: (file: File) => refundsService.uploadProof(id, file), onSuccess: () => { toast.success("Proof attached"); onDone(); }, onError: (e) => toast.error(errorMessage(e)) });
  return <Input type="file" accept="image/png,image/jpeg,image/webp,application/pdf" disabled={upload.isPending} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); }} />;
}
