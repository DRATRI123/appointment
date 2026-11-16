"use client";

import { Suspense, use, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Copy, Download, KeyRound, Link2, LogIn, RefreshCw, Send, ShieldCheck, Unplug } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { ProviderMark } from "@/components/integrations-hub/provider-mark";
import { SettingsForm } from "@/components/integrations-hub/settings-form";
import { StatusPill } from "@/components/integrations-hub/status-pill";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { downloadPrivateFile } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { hubService, type HubDetail } from "@/services/integration-hub";

const OUTCOMES: Record<string, [string, boolean]> = {
  connected: ["Connected. The account was checked.", true],
  denied: ["Not connected: access was not allowed.", false],
  failed: ["Could not connect. Try again and allow every permission the sign-in page asks for.", false],
  invalid_state: ["That sign-in link expired or was already used. Press Connect again.", false],
};

function OAuthResult() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const outcome = params.get("connected") ?? params.get("google");
  useEffect(() => {
    if (!outcome) return;
    const [msg, ok] = OUTCOMES[outcome] ?? OUTCOMES.failed;
    if (ok) toast.success(msg);
    else toast.error(msg);
    queryClient.invalidateQueries({ queryKey: ["hub"] });
    router.replace(pathname);
  }, [outcome, pathname, router, queryClient]);
  return null;
}

export default function IntegrationDetailPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = use(params);
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["hub", "detail", key], queryFn: () => hubService.detail(key) });
  const [shown, setShown] = useState<Record<string, string> | null>(null);
  const set = (d: HubDetail) => {
    queryClient.setQueryData(["hub", "detail", key], d);
    queryClient.invalidateQueries({ queryKey: ["hub"], exact: false, refetchType: "none" });
    if (d.shown_once && Object.keys(d.shown_once).length) setShown(d.shown_once);
  };
  const fail = (e: unknown) => toast.error(errorMessage(e));
  const save = useMutation({ mutationFn: (p: Parameters<typeof hubService.save>[1]) => hubService.save(key, p), onSuccess: (d) => { set(d); toast.success("Saved"); }, onError: fail });
  const toggle = useMutation({ mutationFn: (v: boolean) => hubService.setEnabled(key, v), onSuccess: set, onError: fail });
  const d = query.data;
  const canManage = !!d?.can_manage && hasPermission("integrations:write");

  if (query.isLoading) return <Skeleton className="mx-auto h-96 max-w-5xl" />;
  if (query.error || !d) return <Alert variant="destructive" className="mx-auto max-w-5xl"><AlertDescription>{errorMessage(query.error)}</AlertDescription></Alert>;
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Suspense fallback={null}><OAuthResult /></Suspense>
      <Link href="/admin/integrations" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Integrations</Link>
      <div className="flex flex-wrap items-start gap-4">
        <ProviderMark provider={d.key} category={d.category} className="size-12" />
        <div className="min-w-0 flex-1">
          <PageHeader title={d.name} description={d.description} />
          <div className="-mt-3 flex flex-wrap items-center gap-2 text-sm">
            <StatusPill status={d.status} />
            {d.account ? <span className="text-muted-foreground">· {d.account}</span> : null}
            {d.last_synced_at ? <span className="text-muted-foreground">· last sync {formatDateTime(d.last_synced_at)}</span> : null}
          </div>
        </div>
        {canManage && d.status !== "not_configured" ? (
          <label className="flex items-center gap-2 text-sm">{d.enabled ? "On" : "Off"}<Switch checked={d.enabled} onCheckedChange={(v) => toggle.mutate(v)} aria-label={`Switch ${d.name} on or off`} /></label>
        ) : null}
      </div>
      {d.last_test && !d.last_test.ok ? <Alert variant="destructive"><AlertDescription>Last test {formatDateTime(d.last_test.at)}: {d.last_test.message}</AlertDescription></Alert> : null}
      {d.privacy ? <Alert variant="info"><ShieldCheck aria-hidden /><AlertDescription><span className="font-medium">What is shared: </span>{d.privacy}</AlertDescription></Alert> : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-6">
          {d.fields.length ? (
            <Card>
              <CardHeader><CardTitle className="text-base">Settings</CardTitle><CardDescription>Secrets are stored encrypted and never shown again; leave a secret box empty to keep it. Saving asks you to confirm it is you.</CardDescription></CardHeader>
              <CardContent>
                <SettingsForm key={d.fields.map((f) => `${f.name}:${f.value ?? f.hint ?? ""}`).join("|")} idPrefix={`hub_${d.key}`} fields={d.fields} showSource={false}
                  disabled={!canManage} busy={save.isPending} onSave={(p) => save.mutate(p)} />
              </CardContent>
            </Card>
          ) : null}
          {d.key === "tally" ? <TallyExport detail={d} /> : null}
          {d.syncs.length ? <SyncCard detail={d} onChange={set} canManage={canManage} /> : null}
          {d.key === "n8n" ? <N8nCard detail={d} /> : null}
          <LogsCard detail={d} />
        </div>
        <div className="space-y-6">
          <ConnectionCard detail={d} onChange={set} onShown={setShown} canManage={canManage} />
          <SetupCard detail={d} />
        </div>
      </div>

      <Dialog open={!!shown} onOpenChange={(o) => !o && setShown(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy these secrets now</DialogTitle>
            <DialogDescription>They are shown only this once. Put them in n8n (Header Auth or a Code node that checks the signature).</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {Object.entries(shown ?? {}).map(([k, v]) => <CopyLine key={k} label={k === "incoming_secret" ? "Secret for requests from n8n to this app" : "Secret that signs events sent to n8n"} value={v} />)}
          </div>
          <DialogFooter><Button onClick={() => setShown(null)}>I have copied them</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CopyLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium">{label}</p>
      <div className="flex gap-1">
        <code className="flex-1 truncate rounded-md border bg-muted/50 px-2 py-1.5 text-xs" title={value}>{value}</code>
        <Button type="button" size="sm" variant="outline" aria-label={`Copy: ${label}`} onClick={() => navigator.clipboard.writeText(value).then(() => toast.success("Copied"))}><Copy /></Button>
      </div>
    </div>
  );
}

function ConnectionCard({ detail: d, onChange, onShown, canManage }: { detail: HubDetail; onChange: (d: HubDetail) => void; onShown: (s: Record<string, string>) => void; canManage: boolean }) {
  const [to, setTo] = useState("");
  const [confirm, setConfirm] = useState(false);
  const fail = (e: unknown) => toast.error(errorMessage(e));
  const test = useMutation({
    mutationFn: () => hubService.test(d.key, to),
    onSuccess: (r) => { onChange(r); if (r.test?.ok) toast.success(r.test.message); else toast.error(r.test?.message ?? "Test failed"); },
    onError: fail,
  });
  const connect = useMutation({ mutationFn: () => hubService.connect(d.key, `/admin/integrations/${d.key}`), onSuccess: (r) => window.location.assign(r.url), onError: fail });
  const disconnect = useMutation({ mutationFn: () => hubService.disconnect(d.key), onSuccess: (r) => { onChange(r); setConfirm(false); toast.success("Disconnected"); }, onError: fail });
  const rotate = useMutation({ mutationFn: () => hubService.rotate(d.key), onSuccess: (r) => { onChange(r); if (r.shown_once) onShown(r.shown_once); }, onError: fail });
  const oauth = d.auth === "google" || d.auth === "zoho";
  const connected = ["connected", "error", "untested", "active"].includes(d.status);
  return (
    <Card data-testid="connection-card">
      <CardHeader><CardTitle className="text-base">Connection</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {!canManage ? <p className="text-sm text-muted-foreground">You can view this integration. Changing it needs the right permission.</p> : (
          <>
            {oauth ? (
              <Button className="w-full" onClick={() => connect.mutate()} disabled={connect.isPending} data-testid="hub-connect">
                <LogIn /> {d.status === "connected" ? "Reconnect" : d.auth === "google" ? "Connect Google account" : "Connect Zoho account"}
              </Button>
            ) : null}
            {d.key === "gmail" ? (
              <div className="space-y-1"><Label htmlFor="gmail_to">Send a test email to</Label><Input id="gmail_to" type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="you@example.com" /></div>
            ) : null}
            {d.status !== "not_configured" ? (
              <Button className="w-full" variant="outline" onClick={() => test.mutate()} disabled={test.isPending} data-testid="hub-test"><Send /> {test.isPending ? "Testing…" : "Test connection"}</Button>
            ) : <p className="text-xs text-muted-foreground">Fill in the settings and save, then test.</p>}
            {d.key === "n8n" && d.status !== "not_configured" ? (
              <Button className="w-full" variant="outline" onClick={() => rotate.mutate()} disabled={rotate.isPending}><KeyRound /> Rotate secrets</Button>
            ) : null}
            {connected || d.account ? <Button className="w-full" variant="ghost" onClick={() => setConfirm(true)}><Unplug /> Disconnect</Button> : null}
          </>
        )}
        {d.last_test ? <p className={`text-xs ${d.last_test.ok ? "text-muted-foreground" : "text-destructive"}`}>Last test {formatDateTime(d.last_test.at)}: {d.last_test.message}</p> : null}
      </CardContent>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader><DialogTitle>Disconnect {d.name}?</DialogTitle><DialogDescription>Access is removed and nothing more is sent. Data already in {d.name} stays there.</DialogDescription></DialogHeader>
          <DialogFooter><Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="destructive" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>Disconnect</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

const ENTITY: Record<string, string> = { customer: "Patient", document: "Document", payment: "Payment", refund: "Refund", appointment: "Appointment" };

function SyncCard({ detail: d, onChange, canManage }: { detail: HubDetail; onChange: (d: HubDetail) => void; canManage: boolean }) {
  const fail = (e: unknown) => toast.error(errorMessage(e));
  const retry = useMutation({ mutationFn: (id?: number) => hubService.retry(d.key, id), onSuccess: (r) => { onChange(r); toast.success("Queued again"); }, onError: fail });
  const all = useMutation({ mutationFn: () => hubService.syncAll(d.key), onSuccess: (r) => { onChange(r); toast.success(`${r.queued ?? 0} records queued`); }, onError: fail });
  const counts = [["Sent", d.sync.synced ?? 0], ["Waiting", (d.sync.pending ?? 0) + (d.sync.sending ?? 0)], ["Retrying", d.sync.failed ?? 0], ["Stopped", d.sync.dead ?? 0]] as const;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base"><RefreshCw className="size-4" aria-hidden /> Synchronisation</CardTitle>
        <CardDescription>Sends {d.syncs.map((s) => ENTITY[s]?.toLowerCase() + "s").join(", ")} in the background with retries. A provider being down never blocks a booking.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-4 gap-2 text-center">
          {counts.map(([label, n]) => <div key={label} className="rounded-lg border p-2"><p className="text-lg font-semibold tabular-nums">{n}</p><p className="text-xs text-muted-foreground">{label}</p></div>)}
        </div>
        {canManage ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => all.mutate()} disabled={all.isPending || d.status !== "connected"}>Send all existing records</Button>
            {d.problems.length ? <Button size="sm" variant="outline" onClick={() => retry.mutate(undefined)} disabled={retry.isPending}>Retry all failed</Button> : null}
          </div>
        ) : null}
        {d.problems.length ? (
          <Table>
            <TableHeader><TableRow><TableHead>Record</TableHead><TableHead>Problem</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {d.problems.map((p) => (
                <TableRow key={p.id} data-testid="sync-problem">
                  <TableCell className="text-xs">{ENTITY[p.entity_type] ?? p.entity_type} #{p.entity_id}<span className="block text-muted-foreground">{p.status === "dead" ? "stopped" : `retry ${p.next_attempt_at ? formatDateTime(p.next_attempt_at) : "soon"}`} · {p.attempts} tries</span></TableCell>
                  <TableCell className="max-w-sm text-xs text-destructive">{p.error}</TableCell>
                  <TableCell>{canManage ? <Button size="sm" variant="ghost" onClick={() => retry.mutate(p.id)}>Retry</Button> : null}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : <p className="text-sm text-muted-foreground">No failed records.</p>}
      </CardContent>
    </Card>
  );
}

function TallyExport({ detail: d }: { detail: HubDetail }) {
  const { currentOrganizationId } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const monthStart = today.slice(0, 8) + "01";
  const [from, setFrom] = useState(monthStart);
  const [to, setTo] = useState(today);
  const [again, setAgain] = useState(false);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      await downloadPrivateFile(hubService.tallyUrl(from, to, again), `tally-${from}-${to}.xml`, currentOrganizationId);
      toast.success("Downloaded. In Tally: Gateway of Tally → Import → Vouchers.");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Download className="size-4" aria-hidden /> Export for Tally</CardTitle>
        <CardDescription>Verified payments become receipt vouchers and processed refunds become payment vouchers, dated in the clinic&apos;s time zone.</CardDescription></CardHeader>
      <CardContent className="flex flex-wrap items-end gap-3">
        <div className="space-y-1"><Label htmlFor="tally_from">From</Label><Input id="tally_from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
        <div className="space-y-1"><Label htmlFor="tally_to">To</Label><Input id="tally_to" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
        <label className="flex items-center gap-2 pb-2 text-sm"><Checkbox checked={again} onCheckedChange={(v) => setAgain(!!v)} /> Include vouchers exported before</label>
        <Button onClick={run} disabled={busy || d.status === "not_configured" || !d.enabled} data-testid="tally-export"><Download /> {busy ? "Preparing…" : "Download XML"}</Button>
      </CardContent>
    </Card>
  );
}

function N8nCard({ detail: d }: { detail: HubDetail }) {
  const queryClient = useQueryClient();
  const tasks = useQuery({ queryKey: ["hub", "tasks"], queryFn: () => hubService.tasks("open") });
  const done = useMutation({ mutationFn: hubService.taskDone, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hub", "tasks"] }), onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Link2 className="size-4" aria-hidden /> From n8n to this app</CardTitle>
        <CardDescription>n8n calls this address with an HTTP Request node, signed with the secret shown when you saved (see the setup guide).</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {d.incoming_url ? <CopyLine label="Request URL (POST)" value={d.incoming_url} /> : null}
        <div>
          <p className="mb-1 text-xs font-medium">Actions</p>
          <ul className="space-y-1 text-sm">{Object.entries(d.actions ?? {}).map(([k, v]) => <li key={k}><code className="text-xs">{k}</code> <span className="text-muted-foreground">· {v}</span></li>)}</ul>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium">Open follow-up tasks</p>
          {tasks.data?.length ? (
            <ul className="divide-y rounded-lg border text-sm" data-testid="follow-up-tasks">
              {tasks.data.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <span>{t.title}<span className="block text-xs text-muted-foreground">{t.customer?.name ?? "—"}{t.due_at ? ` · due ${formatDateTime(t.due_at)}` : ""} · {t.source}</span></span>
                  <Button size="sm" variant="ghost" onClick={() => done.mutate(t.id)}>Done</Button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No open tasks.</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function LogsCard({ detail: d }: { detail: HubDetail }) {
  if (!d.logs.length) return null;
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">History</CardTitle><CardDescription>The last 50 connection tests, sign-ins and synchronisations (kept 30 days).</CardDescription></CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow><TableHead>When</TableHead><TableHead>What</TableHead><TableHead>Result</TableHead></TableRow></TableHeader>
          <TableBody>
            {d.logs.map((l, i) => (
              <TableRow key={i} data-testid="hub-log">
                <TableCell className="whitespace-nowrap text-xs">{formatDateTime(l.at)}</TableCell>
                <TableCell className="text-xs">{l.action}{l.duration_ms != null ? <span className="text-muted-foreground"> · {l.duration_ms} ms</span> : null}</TableCell>
                <TableCell className="text-xs">{l.status === "ok" ? <Badge variant="success">ok</Badge> : <span className="text-destructive">{l.error ?? l.status}</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function SetupCard({ detail: d }: { detail: HubDetail }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Setup guide</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        {d.redirect_uri ? <CopyLine label={d.auth === "zoho" ? "Authorized redirect URI (Zoho API Console)" : "Redirect URI (already set by the platform)"} value={d.redirect_uri} /> : null}
        {d.scopes.length ? <div><p className="text-xs font-medium">Permissions asked for</p><ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">{d.scopes.map((s) => <li key={s} className="break-all">{s}</li>)}</ul></div> : null}
        {d.docs ? <p className="text-xs text-muted-foreground">Step-by-step: <code>{d.docs}</code></p> : null}
      </CardContent>
    </Card>
  );
}
