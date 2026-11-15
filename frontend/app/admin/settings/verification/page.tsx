"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, Info, Loader2, Mail, MessageSquareText, Send, ShieldCheck, Trash2, XCircle } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { verificationAdmin, type Channel, type ChannelState, type FieldDef, type OtpPolicy, type VerificationOverview } from "@/services/verification";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { SocialIcon } from "@/components/website/icons";
import { errorMessage } from "@/lib/errors";

const NAMES: Record<Channel, string> = { sms: "SMS", whatsapp: "WhatsApp", email: "Email" };
const ICONS: Record<Channel, React.ReactNode> = { sms: <MessageSquareText className="size-5" />, whatsapp: <SocialIcon network="whatsapp" className="size-5" />, email: <Mail className="size-5" /> };
const PROVIDER_NAMES: Record<string, string> = { msg91: "MSG91 (India, DLT)", twilio: "Twilio", meta: "WhatsApp Business Platform (Meta Cloud API)", smtp: "SMTP email server", console: "Development console" };

export default function VerificationSettingsPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const canWrite = hasPermission("organization:write");
  const overview = useQuery({ queryKey: ["verification", orgId], queryFn: verificationAdmin.overview, enabled: !!orgId });
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="OTP & verification" description="How patients confirm their mobile number or email with a one-time code before an online booking is accepted." />
      <p className="text-sm text-muted-foreground"><Link href="/admin/settings" className="text-primary hover:underline">← Organization settings</Link></p>
      {overview.isLoading ? <Skeleton className="h-96" /> : overview.error ? <Alert variant="destructive"><AlertDescription>{errorMessage(overview.error)}</AlertDescription></Alert> : overview.data ? (
        <>
          <PolicyCard key={JSON.stringify(overview.data.policy)} orgId={orgId!} overview={overview.data} canWrite={canWrite} />
          {overview.data.channels.map((c) => <ChannelCard key={`${c.channel}-${JSON.stringify(c.own)}`} state={c} fields={overview.data.providers[c.channel]} canWrite={canWrite} />)}
        </>
      ) : null}
    </div>
  );
}

function NumberField({ id, label, value, onChange, min, max, suffix, disabled }: { id: string; label: string; value: number; onChange: (v: number) => void; min: number; max: number; suffix?: string; disabled?: boolean }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} type="number" min={min} max={max} value={value} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} className="w-28" />
        {suffix ? <span className="text-sm text-muted-foreground">{suffix}</span> : null}
      </div>
      <p className="text-xs text-muted-foreground">{min}–{max}</p>
    </div>
  );
}

function PolicyCard({ orgId, overview, canWrite }: { orgId: string; overview: VerificationOverview; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [p, setP] = useState<OtpPolicy>(overview.policy);
  const set = (patch: Partial<OtpPolicy>) => setP({ ...p, ...patch });
  const save = useMutation({
    mutationFn: () => verificationAdmin.savePolicy(orgId, p),
    onSuccess: () => { toast.success("Verification settings saved"); void queryClient.invalidateQueries({ queryKey: ["verification", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const usable = new Set(overview.channels.filter((c) => c.usable).map((c) => c.channel));
  const dirty = JSON.stringify(p) !== JSON.stringify(overview.policy);
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-5 text-primary" /> General settings</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <ToggleRow label="One-time codes" hint="Turns the whole feature on or off." checked={p.enabled} onChange={(enabled) => set({ enabled })} disabled={!canWrite} />
          <ToggleRow label="Require verification before a booking is accepted" hint="Recommended: stops fake bookings blocking your calendar." checked={p.required_for_booking} onChange={(v) => set({ required_for_booking: v })} disabled={!canWrite || !p.enabled} />
        </div>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Methods patients can choose</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {(["sms", "whatsapp", "email"] as Channel[]).map((c) => (
              <label key={c} className="flex items-center gap-3 rounded-xl border p-3 text-sm">
                <Checkbox checked={p.channels.includes(c)} disabled={!canWrite} data-testid={`policy-channel-${c}`}
                  onCheckedChange={(on) => { const channels = on ? [...p.channels, c] : p.channels.filter((x) => x !== c); set({ channels, default_channel: channels.includes(p.default_channel) ? p.default_channel : channels[0] ?? "sms" }); }} />
                <span className="text-muted-foreground">{ICONS[c]}</span>
                <span className="flex-1 font-medium">{NAMES[c]}</span>
                {usable.has(c) ? <Badge variant="outline" className="border-emerald-300 text-emerald-700">Ready</Badge> : <Badge variant="outline" className="border-amber-300 text-amber-700">Not set up</Badge>}
              </label>
            ))}
          </div>
          {p.channels.some((c) => !usable.has(c)) ? <p className="text-xs text-amber-700">Methods that are not set up are hidden from patients until a delivery account works.</p> : null}
        </fieldset>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="otp_default">Default method</Label>
            <NativeSelect id="otp_default" value={p.default_channel} disabled={!canWrite} onChange={(e) => set({ default_channel: e.target.value as Channel })}>
              {p.channels.map((c) => <option key={c} value={c}>{NAMES[c]}</option>)}
            </NativeSelect>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="otp_len">Code length</Label>
            <NativeSelect id="otp_len" value={String(p.code_length)} disabled={!canWrite} onChange={(e) => set({ code_length: Number(e.target.value) })}>
              <option value="6">6 digits (recommended)</option><option value="4">4 digits</option>
            </NativeSelect>
          </div>
          <NumberField id="otp_exp" label="Code expires after" value={p.expiry_seconds} min={60} max={900} suffix="seconds" onChange={(v) => set({ expiry_seconds: v })} disabled={!canWrite} />
          <NumberField id="otp_cool" label="Wait before resending" value={p.resend_cooldown_seconds} min={20} max={600} suffix="seconds" onChange={(v) => set({ resend_cooldown_seconds: v })} disabled={!canWrite} />
          <NumberField id="otp_att" label="Wrong attempts allowed" value={p.max_attempts} min={3} max={10} onChange={(v) => set({ max_attempts: v })} disabled={!canWrite} />
          <NumberField id="otp_res" label="Resends per request" value={p.max_resends} min={1} max={10} onChange={(v) => set({ max_resends: v })} disabled={!canWrite} />
        </div>
        <div className="rounded-xl border p-4">
          <p className="mb-3 text-sm font-medium">Abuse limits (per hour)</p>
          <div className="grid gap-4 sm:grid-cols-3">
            <NumberField id="otp_dest" label="Codes to one number or email" value={p.limit_per_destination_hour} min={1} max={10} onChange={(v) => set({ limit_per_destination_hour: v })} disabled={!canWrite} />
            <NumberField id="otp_ip" label="Requests from one network (IP)" value={p.limit_per_ip_hour} min={5} max={200} onChange={(v) => set({ limit_per_ip_hour: v })} disabled={!canWrite} />
            <NumberField id="otp_sess" label="Requests in one booking session" value={p.limit_per_session_hour} min={2} max={30} onChange={(v) => set({ limit_per_session_hour: v })} disabled={!canWrite} />
          </div>
        </div>
        {canWrite ? <div className="flex justify-end"><Button onClick={() => save.mutate()} disabled={!dirty || save.isPending} data-testid="save-otp-policy">{save.isPending ? <Loader2 className="animate-spin" /> : null} Save settings</Button></div> : null}
      </CardContent>
    </Card>
  );
}

function ToggleRow({ label, hint, checked, onChange, disabled }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-start justify-between gap-4 rounded-xl border p-4">
      <span><span className="block text-sm font-medium">{label}</span>{hint ? <span className="block text-xs text-muted-foreground">{hint}</span> : null}</span>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </label>
  );
}

function ChannelCard({ state, fields, canWrite }: { state: ChannelState; fields: Record<string, FieldDef[]>; canWrite: boolean }) {
  const { currentOrganizationId: orgId } = useAuth();
  const queryClient = useQueryClient();
  const providers = Object.keys(fields);
  const [provider, setProvider] = useState(state.own?.provider ?? providers[0]);
  const [enabled, setEnabled] = useState(state.own?.enabled ?? true);
  const [values, setValues] = useState<Record<string, string>>(state.own?.settings ?? {});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [testTo, setTestTo] = useState("");
  const [result, setResult] = useState<{ ok: boolean; error: string | null; provider: string; source: string } | null>(null);
  const refresh = (data: VerificationOverview) => queryClient.setQueryData(["verification", orgId], data);
  const save = useMutation({ mutationFn: () => verificationAdmin.saveProvider(state.channel, { provider, enabled, settings: values, secrets }), onSuccess: (d) => { refresh(d); setSecrets({}); toast.success(`${NAMES[state.channel]} account saved. Send a test to check it.`); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: () => verificationAdmin.removeProvider(state.channel), onSuccess: (d) => { refresh(d); toast.success("Clinic account removed"); }, onError: (e) => toast.error(errorMessage(e)) });
  const test = useMutation({ mutationFn: () => verificationAdmin.test(state.channel, testTo), onSuccess: (r) => { setResult(r); void queryClient.invalidateQueries({ queryKey: ["verification", orgId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const sameProvider = state.own?.provider === provider;
  const status = state.using === "clinic" ? <Badge className="bg-emerald-100 text-emerald-800">Using your account</Badge>
    : state.using === "platform" ? <Badge variant="outline">Using the platform account ({PROVIDER_NAMES[state.platform.provider ?? ""] ?? state.platform.provider})</Badge>
      : <Badge variant="outline" className="border-amber-300 text-amber-700">Not available</Badge>;
  return (
    <Card data-testid={`channel-card-${state.channel}`}>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-3"><span className="text-primary">{ICONS[state.channel]}</span>{NAMES[state.channel]} {status}</CardTitle>
        <CardDescription>
          {state.channel === "whatsapp" ? "Codes on WhatsApp must come from the official WhatsApp Business Platform (or an authorised provider such as Twilio) using a template approved in the Authentication category. A personal WhatsApp number cannot send automated codes."
            : state.channel === "sms" ? "In India, SMS codes need a DLT-registered sender ID and template. Variables: code, then minutes."
              : "Codes by email through your own mail server or provider (SMTP)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`${state.channel}-provider`}>Provider</Label>
            <NativeSelect id={`${state.channel}-provider`} value={provider} disabled={!canWrite} onChange={(e) => { setProvider(e.target.value); setValues(state.own?.provider === e.target.value ? state.own.settings : {}); }}>
              {providers.map((p) => <option key={p} value={p}>{PROVIDER_NAMES[p] ?? p}</option>)}
            </NativeSelect>
          </div>
          <ToggleRow label="Use this account" checked={enabled} onChange={setEnabled} disabled={!canWrite} hint="Off: the platform account is used, if there is one." />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {fields[provider].map((f) => {
            const id = `${state.channel}-${f.key}`;
            const hint = sameProvider ? state.own?.secret_hints[f.key] : undefined;
            if (f.secret) {
              return (
                <div key={f.key} className="space-y-1.5">
                  <Label htmlFor={id}>{f.label}{f.required ? "" : " (optional)"}</Label>
                  <Input id={id} type="password" autoComplete="new-password" value={secrets[f.key] ?? ""} disabled={!canWrite}
                    placeholder={hint ? `Saved (${hint}). Leave empty to keep it.` : "Not set"} onChange={(e) => setSecrets({ ...secrets, [f.key]: e.target.value })} data-testid={`secret-${f.key}`} />
                  <p className="text-xs text-muted-foreground">Stored encrypted. It is never shown again.{f.help ? ` ${f.help}` : ""}</p>
                </div>
              );
            }
            const Multi = f.key === "template";
            return (
              <div key={f.key} className={Multi ? "space-y-1.5 sm:col-span-2" : "space-y-1.5"}>
                <Label htmlFor={id}>{f.label}{f.required ? "" : " (optional)"}</Label>
                {Multi
                  ? <Textarea id={id} rows={4} value={values[f.key] ?? ""} disabled={!canWrite} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                  : <Input id={id} value={values[f.key] ?? ""} disabled={!canWrite} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} data-testid={`field-${f.key}`} />}
                {f.help ? <p className="text-xs text-muted-foreground">{f.help}</p> : null}
              </div>
            );
          })}
        </div>
        {state.own?.missing.length && sameProvider ? <Alert variant="destructive"><Info /><AlertDescription>Missing: {state.own.missing.join(", ")}. Patients can&apos;t use this method until it is complete.</AlertDescription></Alert> : null}
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => save.mutate()} disabled={save.isPending} data-testid={`save-provider-${state.channel}`}>{save.isPending ? <Loader2 className="animate-spin" /> : null} Save account</Button>
            {state.own ? <Button variant="ghost" className="text-destructive" onClick={() => { if (window.confirm(`Remove the clinic's ${NAMES[state.channel]} account? Saved credentials are deleted.`)) remove.mutate(); }}><Trash2 /> Remove</Button> : null}
          </div>
        ) : null}
        <div className="space-y-2 rounded-xl border bg-muted/30 p-4">
          <p className="text-sm font-medium">Send a test</p>
          <p className="text-xs text-muted-foreground">Sends a sample code through {state.using === "clinic" ? "your account" : state.using === "platform" ? "the platform account" : "this channel"} to check delivery. Save changes first.</p>
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); test.mutate(); }}>
            <Input aria-label={`Test ${NAMES[state.channel]} destination`} placeholder={state.channel === "email" ? "you@example.com" : "+91 98250 12345"} value={testTo} onChange={(e) => setTestTo(e.target.value)} disabled={!canWrite || !state.using} />
            <Button type="submit" variant="outline" disabled={!canWrite || !state.using || !testTo.trim() || test.isPending} data-testid={`test-${state.channel}`}>{test.isPending ? <Loader2 className="animate-spin" /> : <Send />} Send test</Button>
          </form>
          {result ? (
            <p className={result.ok ? "flex items-center gap-1.5 text-sm text-emerald-700" : "flex items-start gap-1.5 text-sm text-destructive"} role="status" data-testid={`test-result-${state.channel}`}>
              {result.ok ? <CheckCircle2 className="size-4" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
              {result.ok ? `Accepted by ${PROVIDER_NAMES[result.provider] ?? result.provider}. Check that it arrived.` : `Not sent: ${result.error}`}
            </p>
          ) : state.own?.last_test_at && sameProvider ? (
            <p className="text-xs text-muted-foreground">Last test {new Date(state.own.last_test_at).toLocaleString("en-IN")}: {state.own.last_test_ok ? "accepted" : `failed (${state.own.last_test_error})`}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
