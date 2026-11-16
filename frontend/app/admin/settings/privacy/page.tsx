"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Info } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/errors";

type Values = Record<string, unknown>;

const ROLES: [string, string][] = [
  ["org_owner", "Owner"], ["org_admin", "Administrator"], ["branch_manager", "Branch manager"], ["doctor", "Doctor"],
  ["professional", "Professional"], ["receptionist", "Receptionist"], ["accountant", "Accountant"], ["staff", "Staff"],
];

const SWITCHES: [string, string, string][] = [
  ["mask_contact_details", "Hide patients' mobile numbers and emails", "Staff see 98765XXXXX and atr***@example.com. Roles allowed to see full details press Show, which is recorded."],
  ["reveal_requires_reauth", "Ask “confirm it is you” before showing full details", "Password, authenticator or a code again, at most once per confirmation window."],
  ["doctors_see_own_patients_only", "Doctors see only their own patients", "Doctors and professionals without full appointment access see only patients they have an appointment with."],
  ["watermark_enabled", "Watermark on staff screens and exported PDFs", "Shows an account reference, the time and the session. No names or numbers."],
  ["lock_when_hidden", "Lock as soon as the browser tab is hidden", "Useful for shared reception computers. Staff will unlock more often."],
];

const NUMBERS: [string, string, number, number, number, string][] = [
  ["lock_after_minutes", "Lock the screen after", 1, 240, 1, "minutes without use"],
  ["reauth_window_minutes", "A confirmation lasts", 1, 120, 1, "minutes"],
  ["watermark_opacity", "Watermark strength", 0.03, 0.3, 0.01, "(0.03 very faint – 0.3 strong)"],
  ["max_exports_per_day", "Exports per person per day", 1, 500, 1, "CSV, PDF and document links"],
  ["max_export_rows", "Rows in one export at most", 100, 200000, 100, "rows"],
  ["bulk_access_alert_per_hour", "Alert when one person opens more than", 10, 5000, 1, "patient records in an hour"],
  ["bulk_access_block_per_hour", "Stop record opening above", 20, 20000, 1, "per hour (until the hour passes)"],
];

export default function PrivacySettingsPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const canWrite = hasPermission("organization:write");
  const settings = useQuery({ queryKey: ["settings", orgId], queryFn: () => organizationsService.settings(orgId!), enabled: !!orgId });
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title="Privacy & data protection" description="Who sees patients' contact details, when screens lock, watermarks, printing and export limits." />
      <p className="text-sm text-muted-foreground"><Link href="/admin/settings" className="text-primary hover:underline">← Organization settings</Link></p>
      <Alert variant="info">
        <Info aria-hidden />
        <AlertDescription>
          The server enforces these rules for every screen and API call. Watermarks, print rules and screen lock discourage copying and leave a
          trail, but no website can stop a screenshot, screen recording or a photo of the screen.
        </AlertDescription>
      </Alert>
      {settings.isLoading ? <Skeleton className="h-96" /> : settings.error ? (
        <Alert variant="destructive"><AlertDescription>{errorMessage(settings.error)}</AlertDescription></Alert>
      ) : settings.data ? (
        <PrivacyForm key={settings.dataUpdatedAt} orgId={orgId!} values={settings.data.privacy ?? {}} canWrite={canWrite} />
      ) : null}
    </div>
  );
}

function PrivacyForm({ orgId, values, canWrite }: { orgId: string; values: Values; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Values>(values);
  const set = (key: string, value: unknown) => setDraft((d) => ({ ...d, [key]: value }));
  const byRole = (draft.lock_after_minutes_by_role ?? {}) as Record<string, number>;
  const save = useMutation({
    mutationFn: () => organizationsService.updateSettings(orgId, "privacy", draft),
    onSuccess: () => {
      toast.success("Privacy settings saved");
      queryClient.invalidateQueries({ queryKey: ["settings", orgId] });
      queryClient.invalidateQueries({ queryKey: ["privacy-policy"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="privacy-settings-form">
      <Card>
        <CardHeader><CardTitle>Who sees what</CardTitle><CardDescription>Contact details, doctors&apos; access and watermarks.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {SWITCHES.map(([key, label, hint]) => (
            <div key={key} className="flex items-start justify-between gap-4 rounded-lg border px-4 py-3">
              <div>
                <label htmlFor={`p_${key}`} className="text-sm font-medium">{label}</label>
                <p className="text-xs text-muted-foreground">{hint}</p>
              </div>
              <Switch id={`p_${key}`} checked={!!draft[key]} disabled={!canWrite} onCheckedChange={(v) => set(key, v)} />
            </div>
          ))}
          <div className="space-y-1.5 rounded-lg border px-4 py-3">
            <Label htmlFor="p_print_policy">Printing staff screens</Label>
            <NativeSelect id="p_print_policy" className="max-w-xs" value={String(draft.print_policy ?? "warn")} disabled={!canWrite} onChange={(e) => set("print_policy", e.target.value)}>
              <option value="allow">Allow (recorded)</option>
              <option value="warn">Allow with a confidentiality warning (recorded)</option>
              <option value="block">Print only a notice instead of the page (recorded)</option>
            </NativeSelect>
            <p className="text-xs text-muted-foreground">For a record to share, use Summary PDF on the patient page: it is watermarked and counted as an export.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Screen lock and limits</CardTitle><CardDescription>Numbers outside the allowed range are refused.</CardDescription></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {NUMBERS.map(([key, label, min, max, step, suffix]) => (
            <div key={key} className="space-y-1.5">
              <Label htmlFor={`p_${key}`}>{label}</Label>
              <div className="flex items-center gap-2">
                <Input id={`p_${key}`} type="number" className="w-28" min={min} max={max} step={step} value={Number(draft[key] ?? 0)} disabled={!canWrite} onChange={(e) => set(key, Number(e.target.value))} />
                <span className="text-sm text-muted-foreground">{suffix}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Screen lock by role</CardTitle><CardDescription>Leave empty to use the general time above.</CardDescription></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          {ROLES.map(([code, name]) => (
            <div key={code} className="flex items-center justify-between gap-2">
              <Label htmlFor={`p_role_${code}`}>{name}</Label>
              <div className="flex items-center gap-2">
                <Input id={`p_role_${code}`} type="number" className="w-24" min={1} max={240} placeholder={String(draft.lock_after_minutes ?? 15)}
                  value={byRole[code] ?? ""} disabled={!canWrite}
                  onChange={(e) => {
                    const next = { ...byRole };
                    if (e.target.value === "") delete next[code];
                    else next[code] = Number(e.target.value);
                    set("lock_after_minutes_by_role", next);
                  }} />
                <span className="text-xs text-muted-foreground">min</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Consent and retention</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border px-4 py-3">
            <label htmlFor="p_require_consent_at_booking" className="text-sm font-medium">Ask for consent when booking</label>
            <Switch id="p_require_consent_at_booking" checked={!!draft.require_consent_at_booking} disabled={!canWrite} onCheckedChange={(v) => set("require_consent_at_booking", v)} />
          </div>
          <div className="flex items-center justify-between rounded-lg border px-4 py-3">
            <label htmlFor="p_allow_customer_self_update" className="text-sm font-medium">Patients can update their own details</label>
            <Switch id="p_allow_customer_self_update" checked={!!draft.allow_customer_self_update} disabled={!canWrite} onCheckedChange={(v) => set("allow_customer_self_update", v)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p_consent_text">Consent text</Label>
            <Textarea id="p_consent_text" value={String(draft.consent_text ?? "")} disabled={!canWrite} onChange={(e) => set("consent_text", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p_document_retention_days">Keep patient documents for (days, 0 = keep)</Label>
            <Input id="p_document_retention_days" type="number" className="w-32" min={0} value={Number(draft.document_retention_days ?? 0)} disabled={!canWrite} onChange={(e) => set("document_retention_days", Number(e.target.value))} />
          </div>
        </CardContent>
      </Card>

      {canWrite ? (
        <div className="flex items-center justify-end gap-3">
          <p className="text-xs text-muted-foreground">Saving asks you to confirm it is you.</p>
          <Button type="submit" disabled={save.isPending} data-testid="privacy-save">{save.isPending ? "Saving…" : "Save privacy settings"}</Button>
        </div>
      ) : null}
    </form>
  );
}
