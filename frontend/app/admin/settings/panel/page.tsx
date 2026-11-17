"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Copy, Info, MonitorSmartphone, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { normalizeOrigin } from "@/lib/embed-code";
import { errorMessage } from "@/lib/errors";

const MAX = 5;
// Plain http only for addresses on your own computer while testing (the server refuses them on a real server).
const LOCAL = /^http:\/\/(localhost|127\.0\.0\.1|[a-z0-9-]+\.localhost|[a-z0-9.-]+\.test)(:\d{1,5})?$/;

function normalizeAppOrigin(input: string): string | null {
  const secure = normalizeOrigin(input);
  if (secure) return secure;
  try {
    const url = new URL(input.trim().toLowerCase());
    const origin = `${url.protocol}//${url.host}`;
    return LOCAL.test(origin) ? origin : null;
  } catch {
    return null;
  }
}
const noop = () => () => {};

function useSiteOrigin(): string {
  return useSyncExternalStore(noop, () => window.location.origin, () => "");
}

function panelIframeCode(origin: string, slug: string): string {
  return `<iframe src="${origin}/panel/${slug}" title="Appointments" style="width:100%;height:100vh;border:0"></iframe>`;
}

/** Admin → Panel in your app: show this admin panel inside the clinic's own app (its clinic software). */
export default function PanelSettingsPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const canWrite = hasPermission("organization:write");
  const origin = useSiteOrigin();
  const org = useQuery({ queryKey: ["organization", orgId], queryFn: () => organizationsService.get(orgId!), enabled: !!orgId });
  const settings = useQuery({ queryKey: ["settings", orgId], queryFn: () => organizationsService.settings(orgId!), enabled: !!orgId });
  if (!orgId) return null;
  const saved = settings.data?.panel as { enabled?: boolean; allowed_origins?: string[] } | undefined;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title="Panel in your app" description="Show this admin panel inside your clinic's own app, for example your clinic software, so you see appointments while writing the case paper." />
      <p className="text-sm text-muted-foreground"><Link href="/admin/settings" className="text-primary hover:underline">← Organization settings</Link></p>
      {settings.isLoading || org.isLoading ? <Skeleton className="h-80" /> : settings.error ? (
        <Alert variant="destructive"><AlertDescription>{errorMessage(settings.error)}</AlertDescription></Alert>
      ) : (
        <>
          <PanelForm key={JSON.stringify(saved)} orgId={orgId} canWrite={canWrite} enabled={saved?.enabled === true} initial={saved?.allowed_origins ?? []} />
          {org.data && origin ? <HowTo origin={origin} slug={org.data.slug} on={saved?.enabled === true && (saved?.allowed_origins?.length ?? 0) > 0} /> : null}
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="size-4 text-primary" aria-hidden /> Safety</CardTitle></CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
                <li>Only the addresses listed above can show the panel. Every other website is blocked by the browser.</li>
                <li>People sign in inside the panel. Only owners and administrators can, plus any role you give &quot;Open the admin panel inside the clinic&apos;s own app&quot; in <Link href="/admin/roles" className="text-primary underline underline-offset-4">Roles &amp; permissions</Link>.</li>
                <li>That sign-in works only for this clinic and stays inside the panel: your clinic app never sees it, and it does not sign you in or out anywhere else.</li>
                <li>Switching the panel off, or removing an address or the permission, closes open panels at their next click.</li>
                <li>Screen lock, watermark, &quot;confirm it is you&quot; and the audit log work inside the panel too. Each panel sign-in is in the audit log.</li>
                <li>Both apps keep working on their own: nothing is shared between their databases.</li>
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function PanelForm({ orgId, canWrite, enabled: initialEnabled, initial }: { orgId: string; canWrite: boolean; enabled: boolean; initial: string[] }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(initialEnabled);
  const [origins, setOrigins] = useState<string[]>(initial);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const dirty = enabled !== initialEnabled || origins.join() !== initial.join();
  const save = useMutation({
    mutationFn: () => organizationsService.updateSettings(orgId, "panel", { enabled, allowed_origins: origins }),
    onSuccess: () => { toast.success("Saved. Browsers pick up the change within a minute."); queryClient.invalidateQueries({ queryKey: ["settings", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const add = () => {
    const origin = normalizeAppOrigin(input);
    if (!origin) { setError("Enter the address of your clinic app starting with https://, e.g. https://app.yourclinic.com"); return; }
    if (origins.includes(origin)) { setError("Already in the list."); return; }
    if (origins.length >= MAX) { setError(`You can add up to ${MAX} addresses.`); return; }
    setOrigins([...origins, origin]); setInput(""); setError(null);
  };
  return (
    <Card data-testid="panel-settings">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MonitorSmartphone className="size-5 text-primary" aria-hidden /> Show the admin panel in your app</CardTitle>
        <CardDescription>Switch it on and add the exact web address of your clinic app (where the panel will be shown).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between gap-4 rounded-xl border p-4">
          <div>
            <Label htmlFor="panel_enabled" className="text-sm font-medium">Allow the panel inside my clinic app</Label>
            <p className="text-xs text-muted-foreground">Off: the panel cannot be shown anywhere.</p>
          </div>
          <Switch id="panel_enabled" checked={enabled} onCheckedChange={setEnabled} disabled={!canWrite} data-testid="panel-enabled" />
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">Clinic app addresses</p>
          {origins.length === 0 ? <p className="text-sm text-muted-foreground">No address yet: the panel stays blocked.</p> : (
            <ul className="divide-y rounded-xl border">
              {origins.map((o) => (
                <li key={o} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <span className="break-all font-mono">{o}</span>
                  {canWrite ? <Button type="button" size="icon" variant="ghost" aria-label={`Remove ${o}`} onClick={() => setOrigins(origins.filter((x) => x !== o))}><Trash2 /></Button> : null}
                </li>
              ))}
            </ul>
          )}
          {canWrite ? (
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); add(); }}>
              <div className="flex-1">
                <Input aria-label="Clinic app address" placeholder="https://app.yourclinic.com" value={input} onChange={(e) => { setInput(e.target.value); setError(null); }}
                  aria-invalid={!!error} aria-describedby={error ? "panel-origin-error" : undefined} data-testid="panel-origin-input" />
                {error ? <p id="panel-origin-error" className="mt-1 text-xs text-destructive" role="alert">{error}</p> : null}
              </div>
              <Button type="submit" variant="outline"><Plus /> Add</Button>
            </form>
          ) : null}
          <p className="text-xs text-muted-foreground">Only https:// addresses, exactly as in the browser&apos;s address bar of your clinic app, without a path. While testing on your computer, http://localhost addresses also work.</p>
        </div>
        {canWrite ? (
          <div className="flex items-center justify-end gap-3">
            {dirty ? <Badge variant="outline">Unsaved changes</Badge> : null}
            <Button type="button" disabled={!dirty || save.isPending} onClick={() => save.mutate()} data-testid="panel-save">Save</Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function HowTo({ origin, slug, on }: { origin: string; slug: string; on: boolean }) {
  const link = `${origin}/panel/${slug}`;
  const code = panelIframeCode(origin, slug);
  return (
    <Card data-testid="panel-howto">
      <CardHeader>
        <CardTitle className="text-base">Add it to your clinic app</CardTitle>
        <CardDescription>Put this window (iframe) on a page of your clinic app, for example an &quot;Appointments&quot; menu item. Nothing else is needed in your app.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!on ? <Alert variant="info"><Info /><AlertDescription>Switch the panel on and add your clinic app&apos;s address above first.</AlertDescription></Alert> : null}
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Panel link</p>
          <div className="flex gap-2"><code className="flex-1 truncate rounded-md border bg-muted/50 px-3 py-2 text-xs" data-testid="panel-link">{link}</code><CopyButton text={link} /></div>
        </div>
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Code for your clinic app (HTML)</p>
          <pre className="overflow-auto rounded-xl border bg-muted/50 p-4 text-xs" data-testid="panel-code"><code>{code}</code></pre>
          <CopyButton text={code} label="Copy code" />
        </div>
        <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li>Open that page in your clinic app: the panel asks you to sign in.</li>
          <li>Sign in with your appointment-app email and password (and your authenticator code, if you use one).</li>
          <li>The admin panel opens inside your app. Closing the tab signs the panel out.</li>
        </ol>
        <Alert variant="info">
          <Info />
          <AlertDescription>
            Best: put the appointment app on an address of the same domain as your clinic app, for example clinic app <code>https://yourclinic.com</code> and appointments
            {" "}<code>https://appointments.yourclinic.com</code>. Different domains work too.
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button type="button" variant="outline" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { toast.error("Copy failed. Select the text and copy it."); }
    }}>
      {copied ? <Check /> : <Copy />} {copied ? "Copied" : label}
    </Button>
  );
}
