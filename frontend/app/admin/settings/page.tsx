"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { errorMessage } from "@/lib/errors";
import { titleCase } from "@/lib/format";
import type { Organization } from "@/types/auth";

const NAMESPACES = ["booking", "cancellation", "payment", "notification", "branding", "legal", "general"] as const;

export default function SettingsPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const canWrite = hasPermission("organization:write");
  const org = useQuery({ queryKey: ["organization", orgId], queryFn: () => organizationsService.get(orgId!), enabled: !!orgId });
  const settings = useQuery({ queryKey: ["settings", orgId], queryFn: () => organizationsService.settings(orgId!), enabled: !!orgId });

  if (!orgId) return null;
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Organization settings" description="Profile, booking rules, cancellation policy, payment behaviour, notifications and branding." />
      <p className="-mt-2 mb-4 text-sm">One-time codes for bookings: <Link href="/admin/settings/verification" className="font-medium text-primary hover:underline">OTP &amp; verification</Link></p>
      <Tabs defaultValue="profile">
        <TabsList className="mb-6 flex h-auto flex-wrap">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          {NAMESPACES.map((ns) => <TabsTrigger key={ns} value={ns}>{titleCase(ns)}</TabsTrigger>)}
          <TabsTrigger value="domains">Domains</TabsTrigger>
        </TabsList>
        <TabsContent value="profile">{org.data ? <ProfileForm org={org.data} canWrite={canWrite} /> : <Skeleton className="h-64" />}</TabsContent>
        {NAMESPACES.map((ns) => (
          <TabsContent key={ns} value={ns}>
            {settings.data ? <NamespaceForm key={`${ns}-${settings.dataUpdatedAt}`} orgId={orgId} namespace={ns} values={settings.data[ns] ?? {}} canWrite={canWrite} /> : <Skeleton className="h-64" />}
          </TabsContent>
        ))}
        <TabsContent value="domains"><Domains orgId={orgId} canWrite={canWrite} /></TabsContent>
      </Tabs>
    </div>
  );
}

function ProfileForm({ org, canWrite }: { org: Organization; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: org.name, legal_name: org.legal_name ?? "", business_type: org.business_type ?? "", email: org.email ?? "", phone: org.phone ?? "",
    website: org.website ?? "", logo_url: org.logo_url ?? "", description: org.description ?? "", timezone: org.timezone, currency: org.currency,
  });
  const save = useMutation({
    mutationFn: () => organizationsService.update(org.id, Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" ? null : v])) as Partial<Organization>),
    onSuccess: () => { toast.success("Profile saved"); queryClient.invalidateQueries({ queryKey: ["organization", org.id] }); queryClient.invalidateQueries({ queryKey: ["me"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Shown on your public booking page. Slug: <code>{org.slug}</code> · Code: <code>{org.code}</code></CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="profile-form">
          <Field label="Name" htmlFor="p_name"><Input id="p_name" value={form.name} onChange={set("name")} disabled={!canWrite} /></Field>
          <Field label="Legal name" htmlFor="p_legal"><Input id="p_legal" value={form.legal_name} onChange={set("legal_name")} disabled={!canWrite} /></Field>
          <Field label="Business type" htmlFor="p_type"><Input id="p_type" value={form.business_type} onChange={set("business_type")} disabled={!canWrite} /></Field>
          <Field label="Website" htmlFor="p_web"><Input id="p_web" value={form.website} onChange={set("website")} disabled={!canWrite} /></Field>
          <Field label="Email" htmlFor="p_email"><Input id="p_email" type="email" value={form.email} onChange={set("email")} disabled={!canWrite} /></Field>
          <Field label="Phone" htmlFor="p_phone"><Input id="p_phone" value={form.phone} onChange={set("phone")} disabled={!canWrite} /></Field>
          <Field label="Time zone" htmlFor="p_tz"><Input id="p_tz" value={form.timezone} onChange={set("timezone")} disabled={!canWrite} /></Field>
          <Field label="Currency" htmlFor="p_cur"><Input id="p_cur" maxLength={3} value={form.currency} onChange={set("currency")} disabled={!canWrite} /></Field>
          <Field label="Logo URL" htmlFor="p_logo" className="sm:col-span-2"><Input id="p_logo" value={form.logo_url} onChange={set("logo_url")} disabled={!canWrite} /></Field>
          <Field label="Description" htmlFor="p_desc" className="sm:col-span-2"><Textarea id="p_desc" value={form.description} onChange={set("description")} disabled={!canWrite} /></Field>
          {canWrite ? <div className="sm:col-span-2 flex justify-end"><Button type="submit" disabled={save.isPending}>Save profile</Button></div> : null}
        </form>
      </CardContent>
    </Card>
  );
}

function NamespaceForm({ orgId, namespace, values, canWrite }: { orgId: string; namespace: string; values: Record<string, unknown>; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, unknown>>(values);
  const save = useMutation({
    mutationFn: () => organizationsService.updateSettings(orgId, namespace, draft),
    onSuccess: () => { toast.success(`${titleCase(namespace)} settings saved`); queryClient.invalidateQueries({ queryKey: ["settings", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const entries = Object.entries(draft);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{titleCase(namespace)}</CardTitle>
        <CardDescription>Defaults apply until you change them. Later phases read these values when booking and collecting payments.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid={`settings-${namespace}`}>
          {entries.map(([key, value]) => (
            <SettingInput key={key} id={`${namespace}.${key}`} label={titleCase(key)} value={value} disabled={!canWrite} onChange={(v) => setDraft({ ...draft, [key]: v })} />
          ))}
          {canWrite ? <div className="flex justify-end"><Button type="submit" disabled={save.isPending}>Save</Button></div> : null}
        </form>
      </CardContent>
    </Card>
  );
}

function SettingInput({ id, label, value, disabled, onChange }: { id: string; label: string; value: unknown; disabled: boolean; onChange: (v: unknown) => void }) {
  if (typeof value === "boolean") {
    return (
      <div className="flex items-center justify-between rounded-lg border px-4 py-3">
        <label htmlFor={id} className="text-sm font-medium">{label}</label>
        <Switch id={id} checked={value} disabled={disabled} onCheckedChange={onChange} />
      </div>
    );
  }
  if (typeof value === "number") {
    return <Field label={label} htmlFor={id}><Input id={id} type="number" value={value} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} /></Field>;
  }
  if (Array.isArray(value)) {
    return (
      <Field label={label} htmlFor={id} hint="Comma-separated list">
        <Input id={id} value={value.join(", ")} disabled={disabled} onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean).map((s) => (isNaN(Number(s)) ? s : Number(s))))} />
      </Field>
    );
  }
  if (value !== null && typeof value === "object") {
    return (
      <Field label={label} htmlFor={id} hint="JSON">
        <Textarea id={id} className="font-mono text-xs" defaultValue={JSON.stringify(value, null, 2)} disabled={disabled} onBlur={(e) => { try { onChange(JSON.parse(e.target.value || "{}")); } catch { toast.error(`${label}: invalid JSON`); } }} />
      </Field>
    );
  }
  const str = (value as string | null) ?? "";
  return str.length > 80 || id.startsWith("legal.") ? (
    <Field label={label} htmlFor={id}><Textarea id={id} value={str} disabled={disabled} onChange={(e) => onChange(e.target.value)} /></Field>
  ) : (
    <Field label={label} htmlFor={id}><Input id={id} value={str} disabled={disabled} onChange={(e) => onChange(e.target.value)} /></Field>
  );
}

function Domains({ orgId, canWrite }: { orgId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const domains = useQuery({ queryKey: ["domains", orgId], queryFn: () => organizationsService.domains(orgId) });
  const [domain, setDomain] = useState("");
  const add = useMutation({
    mutationFn: () => organizationsService.addDomain(orgId, { domain: domain.toLowerCase(), is_primary: (domains.data ?? []).length === 0 }),
    onSuccess: () => { toast.success("Domain added. Add the TXT record to verify."); setDomain(""); queryClient.invalidateQueries({ queryKey: ["domains", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => organizationsService.removeDomain(orgId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["domains", orgId] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Custom domains</CardTitle>
        <CardDescription>Serve your booking page from your own domain. Verification by DNS TXT record lands with the public booking site.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {canWrite ? (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <Input placeholder="book.yourclinic.com" value={domain} onChange={(e) => setDomain(e.target.value)} required />
            <Button type="submit" disabled={add.isPending}>Add</Button>
          </form>
        ) : null}
        <ul className="divide-y rounded-lg border">
          {(domains.data ?? []).map((d) => (
            <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
              <div>
                <p className="font-medium">{d.domain} {d.is_primary ? <Badge variant="secondary" className="ml-1">primary</Badge> : null}</p>
                <p className="text-xs text-muted-foreground">TXT _appointment-verify → <code>{d.verification_token}</code></p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={d.is_verified ? "success" : "warning"}>{d.is_verified ? "verified" : "pending"}</Badge>
                {canWrite ? <Button size="sm" variant="ghost" className="text-destructive" onClick={() => remove.mutate(d.id)}>Remove</Button> : null}
              </div>
            </li>
          ))}
          {domains.data?.length === 0 ? <li className="px-4 py-6 text-center text-sm text-muted-foreground">No custom domains yet.</li> : null}
        </ul>
      </CardContent>
    </Card>
  );
}
