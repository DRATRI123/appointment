"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarCheck2, Copy, Link2, RefreshCw, Video } from "lucide-react";
import { integrationsService } from "@/services/integrations";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { MEETING_PROVIDER_LABEL, type MeetingProvider, type ProfessionalConnections } from "@/types/integration";

const KEY = ["integrations"];

/** Which of the doctor's Google calendars receives the bookings (and is read for busy time). */
function CalendarChoice({ integrationId, current, onSave }: { integrationId: string; current: string; onSave: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const list = useQuery({ queryKey: ["google-calendars", integrationId], queryFn: () => integrationsService.calendars(integrationId), enabled: open, retry: false });
  if (!open) {
    return (
      <p className="text-xs text-muted-foreground">
        Calendar: <span className="font-medium text-foreground">{current === "primary" ? "Main calendar" : current}</span>{" "}
        <button type="button" className="text-primary hover:underline" onClick={() => setOpen(true)}>Change</button>
      </p>
    );
  }
  if (list.isLoading) return <p className="text-xs text-muted-foreground">Loading calendars…</p>;
  if (list.error) return <p className="text-xs text-destructive">{errorMessage(list.error)}</p>;
  return (
    <Field label="Add bookings to" htmlFor={`cal_${integrationId}`}>
      <NativeSelect id={`cal_${integrationId}`} value={current} onChange={(e) => { onSave(e.target.value); setOpen(false); }}>
        {current === "primary" ? <option value="primary">Main calendar</option> : null}
        {(list.data ?? []).map((c) => <option key={c.id} value={c.primary ? "primary" : c.id}>{c.name}{c.primary ? " (main)" : ""}</option>)}
      </NativeSelect>
    </Field>
  );
}

export function ProfessionalCard({ row, googleConfigured, zoomConnected, returnTo }: { row: ProfessionalConnections; googleConfigured: boolean; zoomConnected: boolean; returnTo: string }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: KEY });
  const fail = (e: unknown) => toast.error(errorMessage(e));
  const g = row.google;
  const connected = g?.status === "connected" || g?.status === "error";

  const connect = useMutation({ mutationFn: () => integrationsService.connectGoogle(row.professional_id, returnTo), onSuccess: (r) => { window.location.assign(r.authorization_url); }, onError: fail });
  const update = useMutation({ mutationFn: (body: Parameters<typeof integrationsService.update>[1]) => integrationsService.update(g!.id, body), onSuccess: () => { toast.success("Saved"); refresh(); }, onError: fail });
  const test = useMutation({ mutationFn: () => integrationsService.test(g!.id), onSuccess: (r) => { if (r.last_error) toast.error(r.last_error); else toast.success("Calendar connection works"); refresh(); }, onError: fail });
  const sync = useMutation({ mutationFn: () => integrationsService.syncNow(g!.id), onSuccess: () => { toast.success("Busy times refreshed"); refresh(); }, onError: fail });
  const disconnect = useMutation({ mutationFn: () => integrationsService.disconnect(g!.id), onSuccess: () => { toast.success("Google Calendar disconnected"); refresh(); }, onError: fail });

  const [provider, setProvider] = useState<MeetingProvider>(row.meeting.provider);
  const [manualUrl, setManualUrl] = useState(row.meeting.manual_url ?? "");
  const [zoomUser, setZoomUser] = useState(row.meeting.zoom_user ?? "");
  const saveMeeting = useMutation({
    mutationFn: () => integrationsService.setMeeting(row.professional_id, { provider, manual_url: manualUrl || null, zoom_user: zoomUser || null }),
    onSuccess: () => { toast.success("Video link settings saved"); refresh(); }, onError: fail,
  });
  const rotate = useMutation({ mutationFn: () => integrationsService.rotateFeed(row.professional_id), onSuccess: () => { toast.success("New calendar feed link created"); refresh(); }, onError: fail });
  const disableFeed = useMutation({ mutationFn: () => integrationsService.disableFeed(row.professional_id), onSuccess: () => { toast.success("Calendar feed turned off"); refresh(); }, onError: fail });
  const copy = async (text: string) => { try { await navigator.clipboard.writeText(text); toast.success("Copied"); } catch { toast.error("Copy failed; select the link and copy it manually."); } };

  return (
    <Card data-testid="professional-connections">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">{row.professional_name}{row.is_me ? <Badge variant="secondary">You</Badge> : null}</CardTitle>
        <CardDescription>Video for online consultations: <span className="font-medium text-foreground">{MEETING_PROVIDER_LABEL[row.effective_meeting_provider]}</span></CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-3">
        <section className="space-y-3" data-testid="google-section">
          <p className="flex items-center gap-2 font-medium"><CalendarCheck2 className="size-4" /> Google Calendar</p>
          {!connected ? (
            <>
              <p className="text-sm text-muted-foreground">Confirmed appointments appear in this calendar, online ones get a Google Meet link, and busy time in it blocks booking slots.</p>
              <Button onClick={() => connect.mutate()} disabled={!googleConfigured || connect.isPending} data-testid="connect-google">Connect Google Calendar</Button>
              {!googleConfigured ? <p className="text-xs text-muted-foreground">Available once the server administrator sets up Google Calendar access.</p> : null}
            </>
          ) : (
            <>
              <p className="text-sm">{g!.account} {g!.status === "error" ? <Badge variant="destructive">Needs reconnecting</Badge> : g!.is_enabled ? <Badge variant="success">Connected</Badge> : <Badge variant="outline">Paused</Badge>}</p>
              {g!.last_error ? <Alert variant="destructive"><AlertDescription>{g!.last_error}</AlertDescription></Alert> : null}
              <div className="space-y-2 text-sm">
                <label className="flex items-center justify-between gap-3">Sync appointments<Switch checked={g!.is_enabled} onCheckedChange={(v) => update.mutate({ is_enabled: v })} /></label>
                <label className="flex items-center justify-between gap-3">Add Google Meet to online consultations<Switch checked={g!.config.create_meet !== false} onCheckedChange={(v) => update.mutate({ create_meet: v })} /></label>
                <label className="flex items-center justify-between gap-3">Busy time blocks booking slots<Switch checked={g!.config.block_busy !== false} onCheckedChange={(v) => update.mutate({ block_busy: v })} /></label>
                <label className="flex items-center justify-between gap-3">Show patient names in events<Switch checked={g!.config.show_patient_names !== false} onCheckedChange={(v) => update.mutate({ show_patient_names: v })} /></label>
              </div>
              <CalendarChoice integrationId={g!.id} current={String(g!.config.calendar_id ?? "primary")} onSave={(calendar_id) => update.mutate({ calendar_id })} />
              <p className="text-xs text-muted-foreground">Last synced {g!.last_synced_at ? formatDateTime(g!.last_synced_at) : "never"}</p>
              <div className="flex flex-wrap gap-2">
                {g!.status === "error" ? <Button size="sm" onClick={() => connect.mutate()} disabled={connect.isPending}>Reconnect</Button> : null}
                <Button size="sm" variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}><RefreshCw /> Refresh busy times</Button>
                <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>Test</Button>
                <Button size="sm" variant="ghost" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>Disconnect</Button>
              </div>
            </>
          )}
        </section>

        <section className="space-y-3" data-testid="meeting-section">
          <p className="flex items-center gap-2 font-medium"><Video className="size-4" /> Video link</p>
          <Field label="Online consultations use" htmlFor={`mp_${row.professional_id}`}>
            <NativeSelect id={`mp_${row.professional_id}`} value={provider} onChange={(e) => setProvider(e.target.value as MeetingProvider)}>
              {(Object.keys(MEETING_PROVIDER_LABEL) as MeetingProvider[]).map((p) => <option key={p} value={p} disabled={(p === "google_meet" && !connected) || (p === "zoom" && !zoomConnected)}>{MEETING_PROVIDER_LABEL[p]}</option>)}
            </NativeSelect>
          </Field>
          {provider === "auto" ? <p className="text-xs text-muted-foreground">Google Meet if this calendar is connected, otherwise Zoom, otherwise your own link.</p> : null}
          {provider === "manual" || provider === "auto" ? <Field label="Your meeting room link" htmlFor={`mu_${row.professional_id}`} hint="A fixed https:// link, e.g. a personal Meet or Zoom room"><Input id={`mu_${row.professional_id}`} value={manualUrl} onChange={(e) => setManualUrl(e.target.value)} placeholder="https://" /></Field> : null}
          {provider === "zoom" || (provider === "auto" && zoomConnected) ? <Field label="Zoom host email" htmlFor={`zu_${row.professional_id}`} hint="Leave empty to use the clinic's Zoom account"><Input id={`zu_${row.professional_id}`} type="email" value={zoomUser} onChange={(e) => setZoomUser(e.target.value)} /></Field> : null}
          <Button size="sm" onClick={() => saveMeeting.mutate()} disabled={saveMeeting.isPending} data-testid="save-meeting">Save video settings</Button>
        </section>

        <section className="space-y-3" data-testid="feed-section">
          <p className="flex items-center gap-2 font-medium"><Link2 className="size-4" /> Calendar feed</p>
          <p className="text-sm text-muted-foreground">Subscribe from Apple Calendar, Outlook or any calendar app. Anyone with the link sees these appointments, so keep it private.</p>
          {row.feed_url ? (
            <>
              <div className="flex gap-2"><Input readOnly value={row.feed_url} className="font-mono text-xs" onFocus={(e) => e.target.select()} aria-label="Calendar feed link" /><Button size="icon" variant="outline" aria-label="Copy feed link" onClick={() => copy(row.feed_url!)}><Copy /></Button></div>
              <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => rotate.mutate()} disabled={rotate.isPending}>Replace link</Button><Button size="sm" variant="ghost" onClick={() => disableFeed.mutate()} disabled={disableFeed.isPending}>Turn off</Button></div>
            </>
          ) : <Button size="sm" variant="outline" onClick={() => rotate.mutate()} disabled={rotate.isPending} data-testid="create-feed">Create feed link</Button>}
        </section>
      </CardContent>
    </Card>
  );
}
