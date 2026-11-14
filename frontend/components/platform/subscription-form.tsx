"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { platformService } from "@/services/platform";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { MoneyInput } from "@/components/forms/money-input";
import { errorMessage } from "@/lib/errors";
import { SUBSCRIPTION_STATUS_LABEL, type OrgSummary, type Plan, type Subscription } from "@/types/platform";

const toLocalDate = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "");

/** Record a plan change. No money moves here: the platform records what was agreed and paid elsewhere. */
export function SubscriptionForm({ org, plans }: { org: OrgSummary; plans: Plan[] }) {
  const queryClient = useQueryClient();
  const s = org.subscription;
  const [plan, setPlan] = useState(s?.plan_code ?? plans[0]?.code ?? "");
  const [status, setStatus] = useState<Subscription["status"]>(s?.status ?? "active");
  const [trialEnds, setTrialEnds] = useState(toLocalDate(s?.trial_ends_at));
  const [ends, setEnds] = useState(toLocalDate(s?.ends_at));
  const [price, setPrice] = useState<number | null>(s?.price_paise ?? null);
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () => platformService.setSubscription(org.id, { plan_code: plan, status, trial_ends_at: trialEnds ? `${trialEnds}T23:59:59Z` : null, ends_at: ends ? `${ends}T23:59:59Z` : null, price_paise: price, notes: notes || null }),
    onSuccess: () => { toast.success("Subscription recorded"); setNotes(""); ["platform-org", "platform-subs", "platform-history"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!plans.length) return <p className="text-sm text-muted-foreground">Create plans under Subscriptions first.</p>;
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="subscription-form">
      <Field label="Plan" htmlFor="sub_plan"><NativeSelect id="sub_plan" value={plan} onChange={(e) => { setPlan(e.target.value); setPrice(plans.find((p) => p.code === e.target.value)?.price_paise ?? null); }}>{plans.map((p) => <option key={p.code} value={p.code}>{p.name}{p.is_active ? "" : " (retired)"}</option>)}</NativeSelect></Field>
      <Field label="Status" htmlFor="sub_status"><NativeSelect id="sub_status" value={status} onChange={(e) => setStatus(e.target.value as Subscription["status"])}>{Object.entries(SUBSCRIPTION_STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect></Field>
      <Field label="Price per cycle" htmlFor="sub_price"><MoneyInput id="sub_price" valuePaise={price} onChange={setPrice} allowEmpty /></Field>
      {status === "trial" ? <Field label="Trial ends" htmlFor="sub_trial"><Input id="sub_trial" type="date" value={trialEnds} onChange={(e) => setTrialEnds(e.target.value)} /></Field> : <Field label="Paid until" htmlFor="sub_ends"><Input id="sub_ends" type="date" value={ends} onChange={(e) => setEnds(e.target.value)} /></Field>}
      <Field label="Note (e.g. invoice or bank reference)" htmlFor="sub_notes" className="sm:col-span-2"><Textarea id="sub_notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <div className="sm:col-span-2"><Button type="submit" disabled={save.isPending || !plan} data-testid="save-subscription">Record plan change</Button></div>
    </form>
  );
}
