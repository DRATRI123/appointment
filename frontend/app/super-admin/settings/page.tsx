"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import type { Plan, PlatformSettings } from "@/types/platform";

function SettingsForm({ initial, plans }: { initial: PlatformSettings; plans: Plan[] }) {
  const queryClient = useQueryClient();
  const [s, setS] = useState(initial);
  const set = (patch: Partial<PlatformSettings>) => setS((v) => ({ ...v, ...patch }));
  const save = useMutation({ mutationFn: () => platformService.saveSettings(s), onSuccess: () => { toast.success("Platform settings saved"); ["platform-settings", "platform-public"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <Card><CardHeader><CardTitle className="text-base">Identity</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2">
        <Field label="Platform name" htmlFor="ps_name"><Input id="ps_name" value={s.platform_name} onChange={(e) => set({ platform_name: e.target.value })} /></Field>
        <Field label="Support email" htmlFor="ps_support"><Input id="ps_support" type="email" value={s.support_email} onChange={(e) => set({ support_email: e.target.value })} /></Field>
      </CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">Sign-ups and trials</CardTitle><CardDescription>New organizations start on the default plan as a trial. Without a default plan they are unlimited.</CardDescription></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2">
        <label className="flex items-center gap-3 text-sm sm:col-span-2"><Switch checked={s.allow_organization_signup} onCheckedChange={(v) => set({ allow_organization_signup: v })} data-testid="toggle-signup" /> Anyone can create an organization</label>
        <Field label="Default plan for new organizations" htmlFor="ps_plan"><NativeSelect id="ps_plan" value={s.default_plan_code ?? ""} onChange={(e) => set({ default_plan_code: e.target.value || null })}><option value="">None (unlimited)</option>{plans.filter((p) => p.is_active).map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}</NativeSelect></Field>
        <Field label="Trial length (days)" htmlFor="ps_trial"><Input id="ps_trial" type="number" min={0} max={365} value={s.default_trial_days} onChange={(e) => set({ default_trial_days: Number(e.target.value) })} /></Field>
      </CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">Announcement</CardTitle><CardDescription>Shown at the top of every dashboard and booking page until dismissed. Leave empty to hide.</CardDescription></CardHeader><CardContent className="grid gap-4 sm:grid-cols-[1fr_12rem]">
        <Field label="Message" htmlFor="ps_ann"><Textarea id="ps_ann" maxLength={500} value={s.announcement} onChange={(e) => set({ announcement: e.target.value })} placeholder="e.g. Scheduled maintenance on Sunday 2–3 am IST" /></Field>
        <Field label="Style" htmlFor="ps_level"><NativeSelect id="ps_level" value={s.announcement_level} onChange={(e) => set({ announcement_level: e.target.value as PlatformSettings["announcement_level"] })}><option value="info">Information</option><option value="warning">Warning</option></NativeSelect></Field>
      </CardContent></Card>
      <Button type="submit" disabled={save.isPending} data-testid="save-platform-settings">Save settings</Button>
    </form>
  );
}

export default function PlatformSettingsPage() {
  const settings = useQuery({ queryKey: ["platform-settings"], queryFn: platformService.settings });
  const plans = useQuery({ queryKey: ["platform-plans"], queryFn: platformService.plans });
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title="Platform settings" description="Name, sign-up policy, trials and the platform-wide announcement." />
      {settings.data && plans.data ? <SettingsForm key={JSON.stringify(settings.data)} initial={settings.data} plans={plans.data} /> : <Skeleton className="h-96" />}
    </div>
  );
}
