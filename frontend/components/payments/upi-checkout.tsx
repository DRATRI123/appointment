"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Download, Loader2, Paperclip, ShieldCheck, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field } from "@/components/forms/field";
import { PaymentStatusBadge } from "@/components/payments/payment-status-badge";
import { mediaUrl } from "@/services/catalog";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import type { Checkout } from "@/types/payment";

type SubmitData = { utr: string; transaction_reference?: string; paid_at?: string; notes?: string; screenshot?: File | null };

const APPS: [keyof NonNullable<Checkout["upi"]>["app_links"], string][] = [["gpay", "Google Pay"], ["phonepe", "PhonePe"], ["paytm", "Paytm"], ["bhim", "BHIM"]];

export function UpiCheckout({ checkout, onSubmit, compact = false }: { checkout: Checkout; onSubmit?: (data: SubmitData) => Promise<unknown>; compact?: boolean }) {
  const { payment, upi } = checkout;
  const [copied, setCopied] = useState(false);
  const qrSrc = upi?.qr_data_url ?? (upi?.static_qr_url ? mediaUrl(upi.static_qr_url) : undefined);

  return (
    <Card className="border-primary/30" data-testid="upi-checkout">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-lg">Pay {formatPaise(payment.amount_paise)} by UPI</CardTitle>
            <CardDescription>Reference <span className="font-mono">{payment.reference}</span></CardDescription>
          </div>
          <PaymentStatusBadge status={payment.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {checkout.message ? <Alert variant={payment.status === "rejected" ? "destructive" : payment.status === "verified" ? "success" : "info"}><AlertDescription>{checkout.message}</AlertDescription></Alert> : null}

        {upi && checkout.can_submit ? (
          <div className={`grid gap-6 ${compact ? "" : "md:grid-cols-[240px_1fr]"}`}>
            <div className="flex flex-col items-center gap-3">
              {qrSrc ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={qrSrc} alt={`UPI QR code to pay ${upi.merchant_name}`} className="size-56 rounded-xl border bg-white p-2" data-testid="upi-qr" />
              ) : null}
              {qrSrc ? (
                <Button asChild size="sm" variant="outline"><a href={qrSrc} download={`${payment.reference}.png`}><Download /> Download QR</a></Button>
              ) : null}
            </div>
            <div className="space-y-4 text-sm">
              <dl className="grid gap-2">
                <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><dt className="text-muted-foreground">Pay to</dt><dd className="font-medium">{upi.merchant_name}</dd></div>
                <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
                  <dt className="text-muted-foreground">UPI ID</dt>
                  <dd className="flex items-center gap-2 font-mono" data-testid="upi-id">{upi.upi_id}
                    <Button type="button" size="icon" variant="ghost" className="size-7" aria-label="Copy UPI ID" onClick={async () => { try { await navigator.clipboard.writeText(upi.upi_id); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { toast.error("Copy failed. Select the UPI ID manually."); } }}>{copied ? <Check /> : <Copy />}</Button>
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><dt className="text-muted-foreground">Amount</dt><dd className="text-base font-semibold">{formatPaise(payment.amount_paise)}</dd></div>
                {payment.expires_at ? <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><dt className="text-muted-foreground">Pay before</dt><dd><ExpiresIn at={payment.expires_at} /></dd></div> : null}
              </dl>
              {upi.is_static ? <Alert variant="info"><AlertDescription>This QR does not carry the amount. Enter exactly {formatPaise(payment.amount_paise)} and add {payment.reference} in the remarks.</AlertDescription></Alert> : null}
              {upi.instructions ? <p className="whitespace-pre-line text-muted-foreground">{upi.instructions}</p> : null}
              <div className="space-y-2">
                <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground"><Smartphone className="size-3.5" /> On your phone</p>
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm"><a href={upi.app_links.any}>Open UPI app</a></Button>
                  {APPS.map(([k, label]) => <Button key={k} asChild size="sm" variant="outline"><a href={upi.app_links[k]}>{label}</a></Button>)}
                </div>
                <p className="text-xs text-muted-foreground">App buttons work on phones where that app is installed. On a computer, scan the QR with your phone.</p>
              </div>
            </div>
          </div>
        ) : null}

        {checkout.can_submit && onSubmit ? <SubmitForm onSubmit={onSubmit} /> : null}

        {checkout.latest_submission && !checkout.can_submit ? (
          <div className="rounded-lg border bg-muted/30 p-3 text-sm" data-testid="latest-submission">
            <p className="font-medium">Your submission</p>
            <p className="text-muted-foreground">UTR <span className="font-mono">{checkout.latest_submission.utr}</span> · sent {formatDateTime(checkout.latest_submission.created_at)}{checkout.latest_submission.has_screenshot ? " · screenshot attached" : ""}</p>
          </div>
        ) : null}

        <p className="flex items-start gap-2 text-xs text-muted-foreground"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" /> Money goes straight to the clinic&apos;s own bank account. Your booking is confirmed only after their team sees the credit, never from a screenshot alone.</p>
      </CardContent>
    </Card>
  );
}

function ExpiresIn({ at }: { at: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  const mins = Math.round((new Date(at).getTime() - now) / 60000);
  return <span className={mins < 5 ? "font-medium text-destructive" : ""}>{formatDateTime(at)}{mins > 0 ? ` (${mins} min left)` : " (window closed)"}</span>;
}

function SubmitForm({ onSubmit }: { onSubmit: (data: SubmitData) => Promise<unknown> }) {
  const [form, setForm] = useState({ utr: "", transaction_reference: "", paid_at: "", notes: "" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <form
      className="space-y-4 rounded-xl border p-4"
      data-testid="payment-submit-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSubmit({ utr: form.utr, transaction_reference: form.transaction_reference || undefined, paid_at: form.paid_at ? new Date(form.paid_at).toISOString() : undefined, notes: form.notes || undefined, screenshot: file });
          toast.success("Payment details sent for verification");
        } catch (error) {
          toast.error(errorMessage(error));
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <p className="font-medium">Already paid? Tell the clinic</p>
        <p className="text-sm text-muted-foreground">Find the 12-digit UTR (UPI reference number) on the payment success screen in your app.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="UTR / UPI reference number *" htmlFor="pay_utr"><Input id="pay_utr" required inputMode="numeric" autoComplete="off" placeholder="412345678901" value={form.utr} onChange={(e) => setForm({ ...form, utr: e.target.value })} /></Field>
        <Field label="Paid at (optional)" htmlFor="pay_at"><Input id="pay_at" type="datetime-local" value={form.paid_at} onChange={(e) => setForm({ ...form, paid_at: e.target.value })} /></Field>
        <Field label="App transaction ID (optional)" htmlFor="pay_txn"><Input id="pay_txn" value={form.transaction_reference} onChange={(e) => setForm({ ...form, transaction_reference: e.target.value })} /></Field>
        <div className="space-y-2">
          <p className="text-sm font-medium">Screenshot (optional)</p>
          <Button type="button" variant="outline" size="sm" onClick={() => input.current?.click()}><Paperclip /> {file ? file.name : "Attach screenshot"}</Button>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <Field label="Note (optional)" htmlFor="pay_notes" className="sm:col-span-2"><Textarea id="pay_notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
      </div>
      <Button type="submit" disabled={busy || form.utr.trim().length < 6}>{busy ? <Loader2 className="animate-spin" /> : null} Submit for verification</Button>
    </form>
  );
}
