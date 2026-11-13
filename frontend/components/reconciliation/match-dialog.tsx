"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { reconciliationService } from "@/services/reconciliation";
import { paymentsService } from "@/services/payments";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { cn, formatPaise } from "@/lib/utils";
import { PAYMENT_STATUS_LABEL, type PaymentStatus } from "@/types/payment";
import type { BankTransaction } from "@/types/reconciliation";

type Option = { id: string; reference: string; status: string; amount: number; customer: string | null; utr: string | null; score?: number; reasons?: string[] };

export function MatchDialog({ txn, onClose, onDone }: { txn: BankTransaction; onClose: () => void; onDone: () => void }) {
  const candidates = useQuery({ queryKey: ["reconciliation-candidates", txn.id], queryFn: () => reconciliationService.candidates(txn.id) });
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const found = useQuery({ queryKey: ["payments", "match-search", query], queryFn: () => paymentsService.list({ search: query, page_size: 10 }), enabled: query.length >= 3 });
  const [picked, setPicked] = useState<Option | null>(null);
  const [notes, setNotes] = useState("");
  const match = useMutation({
    mutationFn: () => reconciliationService.match(txn.id, picked!.id, notes || undefined),
    onSuccess: () => { toast.success("Matched. Open the payment to verify it if it is still waiting."); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const options: Option[] = query.length >= 3
    ? (found.data?.data ?? []).map((p) => ({ id: p.id, reference: p.reference, status: p.status, amount: p.verified_amount_paise ?? p.amount_paise, customer: p.customer_name, utr: p.latest_utr }))
    : (candidates.data ?? []).map((c) => ({ id: c.payment_id, reference: c.payment_reference, status: c.payment_status, amount: c.amount_paise, customer: c.customer_name, utr: c.latest_utr, score: c.score, reasons: c.reasons }));
  const amountDiffers = picked && picked.amount !== txn.amount_paise;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Match {formatPaise(txn.amount_paise)} credited on {formatDate(txn.transaction_date, "UTC")}</DialogTitle>
          <DialogDescription className="break-words">{txn.utr ? <span className="font-mono">UTR {txn.utr} · </span> : null}{txn.description}</DialogDescription>
        </DialogHeader>
        <form className="relative" onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }}>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search payments by reference, UTR, customer or mobile, then press Enter" value={search} onChange={(e) => { setSearch(e.target.value); if (!e.target.value) setQuery(""); }} />
        </form>
        <p className="text-xs text-muted-foreground">{query.length >= 3 ? `Search results for “${query}”` : "Suggested payments, best first"}</p>
        <div className="max-h-80 space-y-1.5 overflow-y-auto" data-testid="match-options">
          {(query.length >= 3 ? found.isLoading : candidates.isLoading) ? <Skeleton className="h-24" /> : options.length === 0 ? <p className="py-6 text-center text-sm text-muted-foreground">No likely payment. Search above, or ignore this credit if it is not a booking payment.</p> : options.map((o) => (
            <button key={o.id} type="button" onClick={() => setPicked(o)} className={cn("w-full rounded-lg border p-3 text-left text-sm transition-colors hover:bg-muted/50", picked?.id === o.id && "border-primary bg-primary/5")} data-testid="match-option">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-medium">{formatPaise(o.amount)}</span>
                <span>{o.customer}</span>
                <span className="text-xs text-muted-foreground">{PAYMENT_STATUS_LABEL[o.status as PaymentStatus] ?? o.status}</span>
                {o.score !== undefined ? <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs font-medium">{o.score}% likely</span> : null}
              </div>
              <p className="font-mono text-xs text-muted-foreground">{o.reference}{o.utr ? ` · UTR ${o.utr}` : ""}</p>
              {o.reasons?.length ? <p className="text-xs text-muted-foreground">{o.reasons.join(" · ")}</p> : null}
            </button>
          ))}
        </div>
        {amountDiffers ? <Field label="The amounts differ. Why do they belong together?" htmlFor="match_notes"><Textarea id="match_notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field> : null}
        <p className="text-xs text-muted-foreground">Matching records the bank credit as evidence for this payment. It does not verify the payment; a verifier still approves it.{picked ? ` Selected ${picked.reference}.` : ""}</p>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => match.mutate()} disabled={!picked || (!!amountDiffers && notes.trim().length < 3) || match.isPending} data-testid="confirm-match">Confirm match</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function IgnoreDialog({ txn, onClose, onDone }: { txn: BankTransaction; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const ignore = useMutation({ mutationFn: () => reconciliationService.ignore(txn.id, reason), onSuccess: () => { toast.success("Marked as not a booking payment"); onDone(); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ignore this credit?</DialogTitle>
          <DialogDescription>{formatPaise(txn.amount_paise)} on {formatDate(txn.transaction_date, "UTC")}. Use this for credits that are not booking payments, such as supplier refunds or transfers between your own accounts.</DialogDescription>
        </DialogHeader>
        <Field label="Reason" htmlFor="ignore_reason"><Input id="ignore_reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Transfer from savings account" /></Field>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => ignore.mutate()} disabled={reason.trim().length < 3 || ignore.isPending}>Ignore</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
