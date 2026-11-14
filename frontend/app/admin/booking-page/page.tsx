"use client";

import { useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Copy, Download, ExternalLink, Globe, Info, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { bookingUrl, type BookingParams } from "@/lib/booking-params";
import { htmlButtonCode, iframeEmbedCode, liquidButtonCode, normalizeOrigin } from "@/lib/embed-code";
import { errorMessage } from "@/lib/errors";

const noop = () => () => {};

/** The booking page is served by this same web app, so its public address is the address the admin is using now. */
function useSiteOrigin(): string {
  return useSyncExternalStore(noop, () => window.location.origin, () => "");
}

export default function BookingPageAdmin() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const canWrite = hasPermission("organization:write");
  const origin = useSiteOrigin();
  const org = useQuery({ queryKey: ["organization", orgId], queryFn: () => organizationsService.get(orgId!), enabled: !!orgId });
  const settings = useQuery({ queryKey: ["settings", orgId], queryFn: () => organizationsService.settings(orgId!), enabled: !!orgId });
  const services = useQuery({ queryKey: ["services", orgId, "booking-page"], queryFn: () => catalogService.services(), enabled: !!orgId });
  const branches = useQuery({ queryKey: ["branches", orgId, "booking-page"], queryFn: () => catalogService.branches(false), enabled: !!orgId });
  const pros = useQuery({ queryKey: ["professionals", orgId, "booking-page"], queryFn: () => catalogService.professionals(), enabled: !!orgId });
  const [hints, setHints] = useState<BookingParams>({});

  if (!orgId) return null;
  const slug = org.data?.slug;
  const ready = slug && origin;
  const link = ready ? bookingUrl(origin, slug, hints) : "";
  const pageEnabled = settings.data?.general?.booking_page_enabled !== false;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="Booking page & Shopify" description="Share your booking page, add a Book button to your Shopify store or website, or embed the full booking page. No Shopify app needed." />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Globe className="size-5 text-primary" aria-hidden /> Your booking page</CardTitle>
          <CardDescription>Anyone with this link can see your services, doctors and free times and book. It never shows patient information.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!ready ? <Skeleton className="h-10" /> : (
            <>
              {!pageEnabled ? <Alert variant="destructive"><Info /><AlertDescription>Online booking is switched off in Organization settings → General, so visitors see a notice instead of the booking form.</AlertDescription></Alert> : null}
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Preselect service" htmlFor="h_service">
                  <NativeSelect id="h_service" value={hints.service ?? ""} onChange={(e) => setHints({ ...hints, service: e.target.value || undefined })}>
                    <option value="">Visitor chooses</option>
                    {services.data?.filter((s) => s.is_active && s.is_bookable_online !== false).map((s) => <option key={s.id} value={s.slug}>{s.name}</option>)}
                  </NativeSelect>
                </Field>
                <Field label="Preselect location" htmlFor="h_branch">
                  <NativeSelect id="h_branch" value={hints.branch ?? ""} onChange={(e) => setHints({ ...hints, branch: e.target.value || undefined })}>
                    <option value="">Visitor chooses</option>
                    {branches.data?.map((b) => <option key={b.id} value={b.slug}>{b.name}</option>)}
                  </NativeSelect>
                </Field>
                <Field label="Preselect doctor" htmlFor="h_doctor">
                  <NativeSelect id="h_doctor" value={hints.doctor ?? ""} onChange={(e) => setHints({ ...hints, doctor: e.target.value || undefined })}>
                    <option value="">Visitor chooses</option>
                    {pros.data?.filter((p) => p.is_active).map((p) => <option key={p.id} value={p.slug}>{p.display_name}</option>)}
                  </NativeSelect>
                </Field>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input readOnly value={link} aria-label="Booking page link" data-testid="booking-link" className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
                <div className="flex gap-2">
                  <CopyButton text={link} label="Copy link" />
                  <Button asChild variant="outline"><a href={link} target="_blank" rel="noopener noreferrer"><ExternalLink /> Open</a></Button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Preselection only skips a step for the visitor. Prices, free times and who may book are always checked by the server, and unknown values are ignored.
              </p>
            </>
          )}
        </CardContent>
      </Card>

      {ready ? <AddToWebsite origin={origin} slug={slug} hints={hints} /> : null}

      {settings.data ? (
        <>
          <AllowedWebsites key={`embed-${settings.dataUpdatedAt}`} orgId={orgId} canWrite={canWrite}
            initial={(settings.data.embed?.allowed_origins as string[] | undefined) ?? []} />
          <MobileVerification key={`otp-${settings.dataUpdatedAt}`} orgId={orgId} canWrite={canWrite}
            initial={settings.data.booking?.require_mobile_verification !== false} />
        </>
      ) : <Skeleton className="h-48" />}
    </div>
  );
}

function CopyButton({ text, label = "Copy", testId }: { text: string; label?: string; testId?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button type="button" variant="outline" data-testid={testId} onClick={async () => {
      try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { toast.error("Copy failed. Select the text and copy it."); }
    }}>
      {copied ? <Check /> : <Copy />} {copied ? "Copied" : label}
    </Button>
  );
}

function CodeBlock({ code, testId }: { code: string; testId: string }) {
  return (
    <div className="space-y-2">
      <pre className="max-h-80 overflow-auto rounded-xl border bg-muted/50 p-4 text-xs leading-relaxed" data-testid={testId}><code>{code}</code></pre>
      <CopyButton text={code} label="Copy code" testId={`${testId}-copy`} />
    </div>
  );
}

function Steps({ items }: { items: React.ReactNode[] }) {
  return <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">{items.map((item, i) => <li key={i}>{item}</li>)}</ol>;
}

function AddToWebsite({ origin, slug, hints }: { origin: string; slug: string; hints: BookingParams }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Add booking to Shopify or your website</CardTitle>
        <CardDescription>Pick one. The code contains only your public booking address, never a key or password, so it is safe to paste into a theme.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="shopify-button">
          <TabsList className="mb-4 flex h-auto flex-wrap">
            <TabsTrigger value="shopify-button">Shopify button</TabsTrigger>
            <TabsTrigger value="shopify-section">Shopify section</TabsTrigger>
            <TabsTrigger value="iframe">Embed (iframe)</TabsTrigger>
            <TabsTrigger value="html">Any website link</TabsTrigger>
          </TabsList>
          <TabsContent value="shopify-button" className="space-y-4">
            <Steps items={[
              <>In Shopify admin open <b>Online Store → Themes → … → Edit code</b>.</>,
              <>Under <b>Snippets</b> click <b>Add a new snippet</b>, name it <code>appointment-booking-button</code>, and paste the snippet file below.</>,
              <>Paste this line wherever the button should appear (a product template, the header, a page):</>,
            ]} />
            <CodeBlock code={liquidButtonCode(origin, slug, hints)} testId="liquid-code" />
            <Button asChild variant="link" className="h-auto p-0"><a href="/integrations/shopify/appointment-booking-button.liquid" download><Download /> Download the snippet file</a></Button>
          </TabsContent>
          <TabsContent value="shopify-section" className="space-y-4">
            <Steps items={[
              <>Add the snippet as in <b>Shopify button</b>.</>,
              <>Under <b>Sections</b> click <b>Add a new section</b>, name it <code>appointment-booking</code>, and paste the section file.</>,
              <>In the theme editor choose <b>Add section → Appointment booking</b>. Enter <code>{origin}</code> as the booking site address and <code>{slug}</code> as the clinic name.</>,
              <>Choose <b>Book appointment button</b>, or <b>Embedded booking page</b> after adding your store under <b>Allowed websites</b> below.</>,
            ]} />
            <Button asChild variant="outline"><a href="/integrations/shopify/appointment-booking.liquid" download><Download /> Download the section file</a></Button>
          </TabsContent>
          <TabsContent value="iframe" className="space-y-4">
            <Alert variant="info"><ShieldCheck /><AlertDescription>Browsers show the embedded page only on websites listed under <b>Allowed websites</b>. Everywhere else they refuse to load it, which stops other sites from framing your booking page.</AlertDescription></Alert>
            <Steps items={[
              <>Add your store, e.g. <code>https://yourstore.com</code>, under <b>Allowed websites</b>.</>,
              <>In Shopify, add a <b>Custom Liquid</b> section (or edit a page in HTML view) and paste:</>,
            ]} />
            <CodeBlock code={iframeEmbedCode(origin, slug, hints)} testId="iframe-code" />
          </TabsContent>
          <TabsContent value="html" className="space-y-4">
            <p className="text-sm text-muted-foreground">For WordPress, Wix, a Linktree or an email signature: a plain link styled as a button.</p>
            <CodeBlock code={htmlButtonCode(origin, slug, hints)} testId="html-code" />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function AllowedWebsites({ orgId, canWrite, initial }: { orgId: string; canWrite: boolean; initial: string[] }) {
  const queryClient = useQueryClient();
  const [origins, setOrigins] = useState<string[]>(initial);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const dirty = origins.join() !== initial.join();
  const save = useMutation({
    mutationFn: () => organizationsService.updateSettings(orgId, "embed", { allowed_origins: origins }),
    onSuccess: () => { toast.success("Allowed websites saved. Changes reach browsers within a minute."); queryClient.invalidateQueries({ queryKey: ["settings", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const add = () => {
    const origin = normalizeOrigin(input);
    if (!origin) { setError("Enter a website address starting with https://, e.g. https://yourstore.com"); return; }
    if (origins.includes(origin)) { setError("Already in the list."); return; }
    if (origins.length >= 20) { setError("You can allow up to 20 websites."); return; }
    setOrigins([...origins, origin]); setInput(""); setError(null);
  };
  return (
    <Card data-testid="allowed-websites">
      <CardHeader>
        <CardTitle>Allowed websites</CardTitle>
        <CardDescription>
          Websites that may show your booking page inside an iframe. List both your Shopify address and your own domain if visitors use both,
          e.g. <code>https://yourstore.myshopify.com</code> and <code>https://yourstore.com</code>. A link or button works everywhere without being listed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {origins.length === 0 ? <p className="text-sm text-muted-foreground">No websites yet. Embedding is blocked everywhere.</p> : (
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
          <>
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); add(); }}>
              <div className="flex-1">
                <Input aria-label="Website address" placeholder="https://yourstore.com" value={input} onChange={(e) => { setInput(e.target.value); setError(null); }}
                  aria-invalid={!!error} aria-describedby={error ? "origin-error" : undefined} data-testid="origin-input" />
                {error ? <p id="origin-error" className="mt-1 text-xs text-destructive" role="alert">{error}</p> : null}
              </div>
              <Button type="submit" variant="outline"><Plus /> Add</Button>
            </form>
            <div className="flex items-center justify-end gap-3">
              {dirty ? <Badge variant="outline">Unsaved changes</Badge> : null}
              <Button type="button" disabled={!dirty || save.isPending} onClick={() => save.mutate()} data-testid="save-origins">Save allowed websites</Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function MobileVerification({ orgId, canWrite, initial }: { orgId: string; canWrite: boolean; initial: boolean }) {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (on: boolean) => organizationsService.updateSettings(orgId, "booking", { require_mobile_verification: on }),
    onSuccess: (_, on) => { toast.success(on ? "Mobile verification is on" : "Mobile verification is off"); queryClient.invalidateQueries({ queryKey: ["settings", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Mobile verification</CardTitle>
        <CardDescription>Guests confirm their mobile number with a one-time code before an online booking is accepted. This keeps fake bookings from blocking your calendar.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between rounded-lg border px-4 py-3">
          <label htmlFor="require_otp" className="text-sm font-medium">Require a one-time code for online bookings</label>
          <Switch id="require_otp" checked={save.isPending ? save.variables : initial} disabled={!canWrite || save.isPending} onCheckedChange={(on) => save.mutate(on)} />
        </div>
      </CardContent>
    </Card>
  );
}
