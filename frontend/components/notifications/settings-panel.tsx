"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { X } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { notificationsService } from "@/services/notifications";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { CHANNEL_LABEL, type Channel, type EventInfo, type NotificationSettings } from "@/types/notification";

const CHANNEL_TOGGLES: [keyof NotificationSettings, string, string][] = [
  ["email_enabled", "Email", "Sent through your SMTP server."],
  ["sms_enabled", "SMS", "Needs an SMS provider. In India, each SMS template must be DLT registered."],
  ["whatsapp_enabled", "WhatsApp", "Only to customers who opted in. Needs approved WhatsApp templates."],
  ["in_app_enabled", "In-app", "Bell notifications inside the dashboard."],
];

function hoursLabel(h: number) {
  if (h >= 24 && h % 24 === 0) return `${h / 24} day${h === 24 ? "" : "s"} before`;
  if (h < 1) return `${Math.round(h * 60)} min before`;
  return `${h} hour${h === 1 ? "" : "s"} before`;
}

export function SettingsPanel({ initial, events }: { initial: NotificationSettings; events: EventInfo[] }) {
  const { hasPermission } = useAuth();
  const canWrite = hasPermission("notifications:write");
  const queryClient = useQueryClient();
  const [s, setS] = useState<NotificationSettings>(initial);
  const [newHours, setNewHours] = useState("");
  const set = (patch: Partial<NotificationSettings>) => setS((v) => ({ ...v, ...patch }));
  const eventCfg = (e: EventInfo) => s.events[e.code] ?? { enabled: e.enabled, channels: e.channels };
  const setEvent = (e: EventInfo, patch: Partial<{ enabled: boolean; channels: Channel[] }>) => set({ events: { ...s.events, [e.code]: { ...eventCfg(e), ...patch } } });
  const save = useMutation({
    mutationFn: () => notificationsService.saveSettings(s),
    onSuccess: (saved) => { setS(saved); toast.success("Notification settings saved"); ["notification-settings", "notification-events", "notification-providers"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const addHours = () => {
    const h = Number(newHours);
    if (!Number.isFinite(h) || h <= 0) return;
    set({ reminder_hours: [...new Set([...s.reminder_hours, h])].sort((a, b) => b - a).slice(0, 3) });
    setNewHours("");
  };
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Channels</CardTitle><CardDescription>Turn a channel off to stop every message on it, including ones already scheduled.</CardDescription></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {CHANNEL_TOGGLES.map(([key, label, hint]) => (
            <label key={key} className="flex items-start gap-3 rounded-lg border p-3">
              <Switch checked={Boolean(s[key])} onCheckedChange={(v) => set({ [key]: v } as Partial<NotificationSettings>)} disabled={!canWrite} data-testid={`toggle-${key}`} />
              <span><span className="block font-medium">{label}</span><span className="text-xs text-muted-foreground">{hint}</span></span>
            </label>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Reminders and replies</CardTitle><CardDescription>Up to three reminders before each confirmed appointment.</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {s.reminder_hours.map((h) => (
              <span key={h} className="inline-flex items-center gap-1 rounded-full border bg-muted/40 py-1 pr-1 pl-3 text-sm" data-testid="reminder-chip">
                {hoursLabel(h)}
                {canWrite ? <button type="button" aria-label={`Remove ${hoursLabel(h)}`} className="rounded-full p-0.5 hover:bg-muted" onClick={() => set({ reminder_hours: s.reminder_hours.filter((x) => x !== h) })}><X className="size-3.5" /></button> : null}
              </span>
            ))}
            {s.reminder_hours.length === 0 ? <span className="text-sm text-muted-foreground">No reminders</span> : null}
          </div>
          {canWrite && s.reminder_hours.length < 3 ? (
            <form className="flex max-w-sm items-end gap-2" onSubmit={(e) => { e.preventDefault(); addHours(); }}>
              <Field label="Hours before" htmlFor="rem_hours" className="flex-1"><Input id="rem_hours" type="number" min={0.25} max={336} step={0.25} value={newHours} onChange={(e) => setNewHours(e.target.value)} placeholder="e.g. 48" /></Field>
              <Button type="submit" variant="outline">Add</Button>
            </form>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Reply-to email" htmlFor="reply_to" hint="Where customers' replies go. Defaults to the organization email."><Input id="reply_to" type="email" value={s.reply_to_email} onChange={(e) => set({ reply_to_email: e.target.value })} disabled={!canWrite} /></Field>
            <label className="flex items-start gap-3 pt-6 text-sm"><Switch checked={s.notify_staff_on_booking} onCheckedChange={(v) => set({ notify_staff_on_booking: v })} disabled={!canWrite} /> <span>Tell staff about new bookings</span></label>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Messages</CardTitle><CardDescription>Choose which messages go out and on which channels. A channel that is off above is skipped.</CardDescription></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>Message</TableHead><TableHead>On</TableHead>{(["email", "sms", "whatsapp", "in_app"] as Channel[]).map((c) => <TableHead key={c} className="text-center">{CHANNEL_LABEL[c]}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {events.map((e) => {
                const cfg = eventCfg(e);
                const allowed: Channel[] = e.audience === "staff" ? ["email", "in_app"] : ["email", "sms", "whatsapp", "in_app"];
                return (
                  <TableRow key={e.code} data-testid="event-row">
                    <TableCell><span className="font-medium">{e.label}</span><span className="block text-xs text-muted-foreground">{e.audience === "staff" ? "Staff" : "Customer"}</span></TableCell>
                    <TableCell><Switch checked={cfg.enabled} onCheckedChange={(v) => setEvent(e, { enabled: v })} disabled={!canWrite} aria-label={`${e.label} on`} /></TableCell>
                    {(["email", "sms", "whatsapp", "in_app"] as Channel[]).map((c) => (
                      <TableCell key={c} className="text-center">
                        {allowed.includes(c) ? <Checkbox checked={cfg.channels.includes(c)} disabled={!canWrite || !cfg.enabled} aria-label={`${e.label} by ${CHANNEL_LABEL[c]}`}
                          onCheckedChange={(v) => setEvent(e, { channels: v === true ? [...cfg.channels, c] : cfg.channels.filter((x) => x !== c) })} /> : <span className="text-muted-foreground">–</span>}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {canWrite ? <Button onClick={() => save.mutate()} disabled={save.isPending} data-testid="save-notification-settings">Save settings</Button> : null}
    </div>
  );
}
