"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Send, Webhook } from "lucide-react";
import { developersService } from "@/services/developers";
import { SecretReveal } from "@/components/developers/secret-reveal";
import { EmptyState } from "@/components/empty-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { DELIVERY_VARIANT, type WebhookEndpoint } from "@/types/developer";

function EventPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const events = useQuery({ queryKey: ["webhook-events"], queryFn: developersService.events });
  const all = value.includes("*");
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">Events</legend>
      <label className="flex items-center gap-2 text-sm"><Checkbox checked={all} onCheckedChange={(v) => onChange(v === true ? ["*"] : [])} aria-label="All events" /> All events, including ones added later</label>
      {!all ? (
        <div className="grid gap-1.5 sm:grid-cols-2">
          {events.data?.filter((e) => e.name !== "ping").map((e) => (
            <label key={e.name} className="flex items-start gap-2 text-sm">
              <Checkbox checked={value.includes(e.name)} onCheckedChange={(v) => onChange(v === true ? [...value, e.name] : value.filter((x) => x !== e.name))} aria-label={e.name} />
              <span><span className="font-mono text-xs">{e.name}</span><span className="block text-xs text-muted-foreground">{e.description}</span></span>
            </label>
          ))}
        </div>
      ) : null}
    </fieldset>
  );
}

function DeliveriesSheet({ endpoint, onClose }: { endpoint: WebhookEndpoint; onClose: () => void }) {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["webhook-deliveries", endpoint.id], queryFn: () => developersService.deliveries(endpoint.id, { page_size: 50 }) });
  const [open, setOpen] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["webhook-delivery", open], queryFn: () => developersService.delivery(open!), enabled: !!open });
  const redeliver = useMutation({ mutationFn: (id: string) => developersService.redeliver(id), onSuccess: () => { toast.success("Queued for delivery"); queryClient.invalidateQueries({ queryKey: ["webhook-deliveries"] }); queryClient.invalidateQueries({ queryKey: ["webhook-delivery"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const d = detail.data;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-2xl">
        <SheetHeader><SheetTitle>Deliveries · {endpoint.name}</SheetTitle><SheetDescription className="break-all">{endpoint.url}</SheetDescription></SheetHeader>
        {!list.data ? <Skeleton className="h-48" /> : list.data.data.length === 0 ? <p className="text-sm text-muted-foreground">Nothing sent yet. Use “Send test” to try the endpoint.</p> : (
          <Table className="text-xs" data-testid="deliveries-table">
            <TableHeader><TableRow><TableHead>When</TableHead><TableHead>Event</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Response</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.data.data.map((r) => (
                <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(r.id)}>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.last_attempt_at ?? r.created_at)}</TableCell>
                  <TableCell className="font-mono">{r.event}</TableCell>
                  <TableCell><Badge variant={DELIVERY_VARIANT[r.status]}>{r.status}</Badge>{r.attempts > 1 ? <span className="ml-1 text-muted-foreground">×{r.attempts}</span> : null}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.response_status ?? (r.last_error ? "error" : "—")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {d ? (
          <div className="space-y-3 rounded-xl border p-4 text-sm" data-testid="delivery-detail">
            <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-mono text-xs">{d.event_id}</p>{["dead", "failed", "retrying"].includes(d.status) ? <Button size="sm" variant="outline" onClick={() => redeliver.mutate(d.id)}>Send again</Button> : null}</div>
            {d.last_error ? <p className="text-destructive">{d.last_error}</p> : null}
            {d.next_attempt_at && d.status === "retrying" ? <p className="text-muted-foreground">Next attempt {formatDateTime(d.next_attempt_at)}</p> : null}
            <p className="font-medium">Payload</p>
            <pre className="max-h-64 overflow-auto rounded-lg bg-muted/50 p-3 text-xs">{JSON.stringify(d.payload, null, 2)}</pre>
            {d.response_body ? <><p className="font-medium">Response ({d.response_status})</p><pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/50 p-3 text-xs">{d.response_body}</pre></> : null}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

export function WebhooksPanel() {
  const queryClient = useQueryClient();
  const endpoints = useQuery({ queryKey: ["webhooks"], queryFn: developersService.webhooks });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", url: "https://", events: ["appointment.created", "appointment.cancelled"] as string[] });
  const [secret, setSecret] = useState<string | null>(null);
  const [viewing, setViewing] = useState<WebhookEndpoint | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["webhooks"] });
  const fail = (e: unknown) => toast.error(errorMessage(e));
  const create = useMutation({ mutationFn: () => developersService.createWebhook(form), onSuccess: (r) => { setSecret(r.secret); setOpen(false); setForm({ name: "", url: "https://", events: ["appointment.created", "appointment.cancelled"] }); refresh(); }, onError: fail });
  const toggle = useMutation({ mutationFn: (e: WebhookEndpoint) => developersService.updateWebhook(e.id, { is_active: !e.is_active }), onSuccess: refresh, onError: fail });
  const test = useMutation({ mutationFn: (id: string) => developersService.test(id), onSuccess: (r) => { if (r.status === "delivered") toast.success(`Test delivered (HTTP ${r.response_status})`); else toast.error(r.last_error ?? "Test failed"); refresh(); }, onError: fail });
  const rotate = useMutation({ mutationFn: (id: string) => developersService.rotateSecret(id), onSuccess: (r) => setSecret(r.detail), onError: fail });
  const remove = useMutation({ mutationFn: (id: string) => developersService.deleteWebhook(id), onSuccess: () => { toast.success("Endpoint deleted"); refresh(); }, onError: fail });
  return (
    <div className="space-y-4">
      {secret ? <SecretReveal label="Signing secret" value={secret} onDone={() => setSecret(null)} /> : null}
      <div className="flex justify-end">{!open ? <Button onClick={() => setOpen(true)} data-testid="new-webhook"><Plus /> Add endpoint</Button> : null}</div>
      {open ? (
        <Card><CardHeader><CardTitle className="text-base">New webhook endpoint</CardTitle><CardDescription>We POST signed JSON to this URL when the selected events happen, and retry for about two days if it fails.</CardDescription></CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
              <div className="grid gap-4 sm:grid-cols-[14rem_1fr]">
                <Field label="Name" htmlFor="w_name"><Input id="w_name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
                <Field label="URL" htmlFor="w_url" hint="Must be https and reachable from the internet"><Input id="w_url" type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>
              </div>
              <EventPicker value={form.events} onChange={(events) => setForm({ ...form, events })} />
              <div className="flex gap-2"><Button type="submit" disabled={create.isPending || form.name.trim().length < 2 || !form.events.length} data-testid="create-webhook">Add endpoint</Button><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
            </form>
          </CardContent></Card>
      ) : null}
      {endpoints.isLoading ? <Skeleton className="h-40" /> : !endpoints.data?.length ? <EmptyState icon={Webhook} title="No webhooks yet" body="Send bookings and payment updates to your CRM, website or automation tool as they happen." /> : endpoints.data.map((e) => (
        <Card key={e.id} className="py-4" data-testid="webhook-card">
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0"><p className="font-medium">{e.name} {e.is_active ? <Badge variant="success">Active</Badge> : <Badge variant={e.disabled_at ? "destructive" : "outline"}>{e.disabled_at ? "Switched off after failures" : "Paused"}</Badge>}</p><p className="break-all font-mono text-xs text-muted-foreground">{e.url}</p></div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => test.mutate(e.id)} disabled={test.isPending} data-testid="test-webhook"><Send /> Send test</Button>
                <Button size="sm" variant="outline" onClick={() => setViewing(e)}>Deliveries</Button>
                <Button size="sm" variant="ghost" onClick={() => toggle.mutate(e)}>{e.is_active ? "Pause" : "Resume"}</Button>
                <Button size="sm" variant="ghost" onClick={() => { if (confirm("Replace the signing secret? Your receiver must use the new one immediately.")) rotate.mutate(e.id); }}>Rotate secret</Button>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Delete "${e.name}"?`)) remove.mutate(e.id); }}>Delete</Button>
              </div>
            </div>
            {e.disabled_at ? <Alert variant="destructive"><AlertDescription>Switched off on {formatDateTime(e.disabled_at)} after repeated failures. Fix the receiver, then resume.</AlertDescription></Alert> : null}
            <p className="text-xs text-muted-foreground">{e.events.includes("*") ? "All events" : e.events.join(" · ")} · last 7 days: {e.delivered_7d} delivered, {e.failed_7d} failed</p>
          </CardContent>
        </Card>
      ))}
      {viewing ? <DeliveriesSheet endpoint={viewing} onClose={() => setViewing(null)} /> : null}
    </div>
  );
}
