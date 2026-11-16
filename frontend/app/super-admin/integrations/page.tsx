"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Activity, ChevronDown, ChevronUp, Cloud, Copy, Download, FileCog, HardDrive, Info, Mail, MessageSquareText, Send, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusPill } from "@/components/integrations-hub/status-pill";
import { SettingsForm } from "@/components/integrations-hub/settings-form";
import { SocialIcon } from "@/components/website/icons";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadPrivateFile } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { platformIntegrations, type PlatformIntegrations, type PlatformSection, type StorageUsage } from "@/services/platform-integrations";

const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Cloud storage", keys: ["storage", "backup"] },
  { title: "Google services", keys: ["google"] },
  { title: "Messages (platform defaults)", keys: ["email", "sms", "whatsapp"] },
  { title: "Monitoring", keys: ["monitoring"] },
];

const ICONS: Record<string, React.ReactNode> = {
  storage: <HardDrive className="size-5" />,
  backup: <Cloud className="size-5" />,
  google: <span className="text-base font-bold" aria-hidden>G</span>,
  email: <Mail className="size-5" />,
  sms: <MessageSquareText className="size-5" />,
  whatsapp: <SocialIcon network="whatsapp" className="size-5" />,
  monitoring: <Activity className="size-5" />,
};

function bytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export default function PlatformIntegrationsPage() {
  const query = useQuery({
    queryKey: ["platform-integrations"],
    queryFn: platformIntegrations.overview,
    refetchInterval: (q) => (["queued", "running"].includes(q.state.data?.storage.migration.status ?? "") ? 3000 : false),
  });
  const data = query.data;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title="Integrations" description="Platform-wide connections: file storage, backups, Google, default message providers and error tracking." />
      {query.isLoading ? <Skeleton className="h-96" /> : query.error ? (
        <Alert variant="destructive"><AlertDescription>{errorMessage(query.error)}</AlertDescription></Alert>
      ) : data ? (
        <>
          <Summary data={data} />
          <EnvCard data={data} />
          {GROUPS.map((g) => (
            <section key={g.title} className="space-y-3" aria-labelledby={`grp-${g.title}`}>
              <h2 id={`grp-${g.title}`} className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{g.title}</h2>
              <div className="grid gap-4">
                {g.keys.map((k) => {
                  const section = data.sections.find((s) => s.key === k);
                  return section ? <SectionCard key={k} section={section} data={data} /> : null;
                })}
              </div>
            </section>
          ))}
        </>
      ) : null}
    </div>
  );
}

function Summary({ data }: { data: PlatformIntegrations }) {
  const tiles = [
    ["Integrations", data.summary.total],
    ["Connected", data.summary.connected],
    ["Need attention", data.summary.errors],
    ["Not set up", data.summary.not_configured],
  ] as const;
  return (
    <div className="grid gap-3 sm:grid-cols-4" data-testid="integration-summary">
      {tiles.map(([label, value]) => (
        <Card key={label}><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="text-2xl font-semibold tabular-nums">{value}</p></CardContent></Card>
      ))}
    </div>
  );
}

function EnvCard({ data }: { data: PlatformIntegrations }) {
  const [busy, setBusy] = useState(false);
  const write = useMutation({
    mutationFn: platformIntegrations.writeEnv,
    onSuccess: (r) => toast.success(`Written to ${r.path}. Old file kept as ${r.backup}. Restart the app to read it.`),
    onError: (e) => toast.error(errorMessage(e)),
  });
  async function download(withSecrets: boolean) {
    setBusy(true);
    try {
      await downloadPrivateFile(platformIntegrations.envUrl(withSecrets), "integrations.env");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base"><FileCog className="size-4" aria-hidden /> .env or this panel</CardTitle>
        <CardDescription>
          Each setting can come from the server&apos;s <code>.env</code> file or from this panel. A value saved here wins; press
          “use .env” next to a field to go back to the <code>.env</code> value. Secrets are encrypted and never shown again.
          The database address and the encryption keys stay in <code>.env</code> only.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => download(false)} data-testid="env-download"><Download /> Download as .env lines</Button>
        <Button variant="outline" size="sm" disabled={busy} onClick={() => download(true)}><ShieldCheck /> Include secrets</Button>
        {data.environment === "development" ? (
          <Button variant="outline" size="sm" disabled={write.isPending} onClick={() => write.mutate()} data-testid="env-write"><FileCog /> Also save into backend/.env</Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SectionCard({ section, data }: { section: PlatformSection; data: PlatformIntegrations }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(section.status === "error");
  const [to, setTo] = useState("");
  const set = (d: PlatformIntegrations) => queryClient.setQueryData(["platform-integrations"], d);
  const save = useMutation({
    mutationFn: (payload: Parameters<typeof platformIntegrations.save>[1]) => platformIntegrations.save(section.key, payload),
    onSuccess: (d) => { set(d); toast.success("Saved. Press Test to check the connection."); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const test = useMutation({
    mutationFn: () => platformIntegrations.test(section.key, to),
    onSuccess: (r) => { set(r.overview); if (r.ok) toast.success(r.message); else toast.error(r.message); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const needsTo = ["email", "sms"].includes(section.key);
  const fieldKey = section.fields.map((f) => `${f.name}:${f.source}:${f.value ?? f.hint ?? ""}`).join("|");
  return (
    <Card data-testid={`section-${section.key}`}>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="flex min-w-0 gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">{ICONS[section.key]}</span>
          <div className="min-w-0">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">{section.title} <StatusPill status={section.status} /></CardTitle>
            <CardDescription className="mt-1">{section.description}</CardDescription>
            {section.last_test ? (
              <p className={`mt-1 text-xs ${section.last_test.ok ? "text-muted-foreground" : "text-destructive"}`}>
                Last test {formatDateTime(section.last_test.at)}: {section.last_test.message}
              </p>
            ) : null}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={`body-${section.key}`}>
          {open ? <ChevronUp /> : <ChevronDown />} {open ? "Close" : "Configure"}
        </Button>
      </CardHeader>
      {open ? (
        <CardContent id={`body-${section.key}`} className="space-y-5 border-t pt-5">
          {section.key === "storage" ? <StorageControls data={data} section={section} /> : null}
          {section.key === "google" ? (
            <div className="grid gap-2 sm:grid-cols-2">
              <CopyField label="Authorized redirect URI (add to Google Cloud Console)" value={data.google.calendar_redirect_uri} />
              <CopyField label="Authorized JavaScript origin (for Sign in with Google)" value={data.google.javascript_origin} />
            </div>
          ) : null}
          {section.key === "whatsapp" ? <CopyField label="Webhook callback URL (Meta App → WhatsApp → Configuration)" value={data.whatsapp_webhook_url} /> : null}
          <SettingsForm key={fieldKey} idPrefix={section.key} fields={section.fields} busy={save.isPending} onSave={(p) => save.mutate(p)} />
          <div className="flex flex-wrap items-end gap-3 rounded-lg bg-muted/50 p-3">
            {needsTo ? (
              <div className="space-y-1">
                <Label htmlFor={`${section.key}_to`}>{section.key === "email" ? "Send a test email to" : "Send a test SMS to"}</Label>
                <Input id={`${section.key}_to`} className="w-64" value={to} onChange={(e) => setTo(e.target.value)} placeholder={section.key === "email" ? "you@example.com" : "+9198…"} />
              </div>
            ) : null}
            <Button variant="outline" onClick={() => test.mutate()} disabled={test.isPending || section.missing.length > 0} data-testid={`test-${section.key}`}>
              <Send /> {test.isPending ? "Testing…" : "Test connection"}
            </Button>
            {section.missing.length ? <p className="text-xs text-muted-foreground">Fill in first: {section.missing.join(", ")}.</p> : null}
            {section.restart_needed ? <p className="text-xs text-muted-foreground">Takes effect after the API and worker restart.</p> : null}
          </div>
          <p className="text-xs text-muted-foreground"><Info className="mr-1 inline size-3.5" aria-hidden />Setup guide: <code>{section.docs}</code></p>
        </CardContent>
      ) : null}
    </Card>
  );
}

function CopyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium">{label}</p>
      <div className="flex gap-1">
        <code className="flex-1 truncate rounded-md border bg-muted/50 px-2 py-1.5 text-xs" title={value}>{value}</code>
        <Button type="button" size="sm" variant="outline" aria-label={`Copy ${label}`} onClick={() => navigator.clipboard.writeText(value).then(() => toast.success("Copied"))}><Copy /></Button>
      </div>
    </div>
  );
}

function StorageControls({ data, section }: { data: PlatformIntegrations; section: PlatformSection }) {
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState<"local" | "s3" | null>(null);
  const [usage, setUsage] = useState<StorageUsage | null>(null);
  const m = data.storage.migration;
  const running = m.status === "queued" || m.status === "running";
  const target = data.storage.active === "local" ? "s3" : "local";
  const switchIt = useMutation({
    mutationFn: (t: "local" | "s3") => platformIntegrations.switchStorage(t),
    onSuccess: (d) => { queryClient.setQueryData(["platform-integrations"], d); setConfirm(null); toast.success("Moving files. You can leave this page; the worker continues."); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const finish = useMutation({
    mutationFn: platformIntegrations.finishStorage,
    onSuccess: (d) => { queryClient.setQueryData(["platform-integrations"], d); toast.success("Finished. Old copies were not deleted."); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const loadUsage = useMutation({ mutationFn: platformIntegrations.usage, onSuccess: setUsage, onError: (e) => toast.error(errorMessage(e)) });
  useEffect(() => {
    if (m.status === "done") queryClient.invalidateQueries({ queryKey: ["platform-integrations"] });
  }, [m.status, queryClient]);
  const pct = m.total ? Math.round((((m.copied ?? 0) + (m.skipped ?? 0)) / m.total) * 100) : 0;
  return (
    <div className="space-y-3 rounded-lg border p-4" data-testid="storage-controls">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        In use now: <Badge variant="secondary" data-testid="storage-active">{data.storage.active === "local" ? "This server's disk" : "S3-compatible bucket"}</Badge>
        {data.storage.fallback ? <Badge variant="warning">also reading the old {data.storage.fallback} storage</Badge> : null}
        <Button size="sm" variant="ghost" onClick={() => loadUsage.mutate()} disabled={loadUsage.isPending}>{loadUsage.isPending ? "Counting…" : "Show usage"}</Button>
      </div>
      {usage ? (
        <p className="text-sm text-muted-foreground">
          {usage.private.files} private files ({bytes(usage.private.bytes)}) · {usage.public.files} public images ({bytes(usage.public.bytes)}){usage.truncated ? " · counted up to 200,000 files" : ""}
        </p>
      ) : null}
      {running ? (
        <div className="space-y-1" role="status" aria-live="polite">
          <p className="text-sm">Moving files to {m.target === "s3" ? "the bucket" : "this server"}: {(m.copied ?? 0) + (m.skipped ?? 0)} of {m.total || "…"} ({bytes(m.bytes ?? 0)} copied)</p>
          <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} /></div>
        </div>
      ) : null}
      {m.status === "failed" ? <Alert variant="destructive"><AlertDescription>The move stopped and nothing was switched: {m.error}. Press the button again to continue.</AlertDescription></Alert> : null}
      {m.status === "done" && m.finished_at ? <p className="text-sm text-muted-foreground">Last move finished {formatDateTime(m.finished_at)}: {m.copied} copied, {m.skipped} already there.</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={running || (target === "s3" && section.status !== "connected")} onClick={() => setConfirm(target)} data-testid="storage-switch">
          {target === "s3" ? "Move files to the bucket and switch" : "Move files back to this server and switch"}
        </Button>
        {data.storage.fallback && !running ? <Button size="sm" variant="outline" onClick={() => finish.mutate()} disabled={finish.isPending}>Finish (stop reading the old storage)</Button> : null}
      </div>
      {target === "s3" && section.status !== "connected" ? <p className="text-xs text-muted-foreground">Save the bucket settings below and pass the test first.</p> : null}
      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Move every file and switch?</DialogTitle>
            <DialogDescription>
              Every file is copied and checked one by one. The switch happens only after all copies match. Nothing is deleted from the
              current storage. Bookings keep working during the move.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button onClick={() => confirm && switchIt.mutate(confirm)} disabled={switchIt.isPending} data-testid="storage-switch-confirm">Start moving</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
