"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { notificationsService } from "@/services/notifications";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Segmented } from "@/components/ui/segmented";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { CHANNEL_LABEL, type Channel, type EventInfo, type NotificationTemplate } from "@/types/notification";

const PROVIDER_ID_HINT: Partial<Record<Channel, string>> = {
  sms: "DLT template / MSG91 flow id. Indian operators only deliver SMS that match a DLT-registered template.",
  whatsapp: "Approved WhatsApp template name (Meta: name or name:language; Twilio: Content SID). Variables are sent in the order they first appear in the message.",
};

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function TemplateEditor({ event, templates, onClose }: { event: EventInfo; templates: NotificationTemplate[]; onClose: () => void }) {
  const channels = templates.map((t) => t.channel);
  const [channel, setChannel] = useState<Channel>(channels.includes("email") ? "email" : channels[0]);
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-3xl">
        <SheetHeader>
          <SheetTitle>{event.label}</SheetTitle>
          <SheetDescription>{event.description}</SheetDescription>
        </SheetHeader>
        <div className="max-w-full shrink-0 overflow-x-auto">
          <Segmented label="Channel" value={channel} onChange={setChannel} options={channels.map((c) => [c, `${CHANNEL_LABEL[c]}${templates.find((t) => t.channel === c)?.is_custom ? " •" : ""}`] as const)} />
        </div>
        <ChannelForm key={channel} event={event} template={templates.find((t) => t.channel === channel)!} />
      </SheetContent>
    </Sheet>
  );
}

function ChannelForm({ event, template }: { event: EventInfo; template: NotificationTemplate }) {
  const { hasPermission } = useAuth();
  const canWrite = hasPermission("notifications:write");
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState(template.subject ?? "");
  const [body, setBody] = useState(template.body);
  const [providerId, setProviderId] = useState(template.provider_template_id ?? "");
  const [active, setActive] = useState(template.is_active);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const hasSubject = template.channel === "email" || template.channel === "in_app";
  const debounced = useDebounced({ subject, body }, 350);
  const preview = useQuery({
    queryKey: ["template-preview", event.code, template.channel, debounced],
    queryFn: () => notificationsService.preview(event.code, template.channel, { subject: hasSubject ? debounced.subject : null, body: debounced.body }),
    enabled: debounced.body.trim().length > 0,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["notification-templates"] });
  const save = useMutation({
    mutationFn: () => notificationsService.saveTemplate(event.code, template.channel, { subject: hasSubject ? subject : null, body, provider_template_id: providerId || null, is_active: active }),
    onSuccess: () => { toast.success("Template saved"); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reset = useMutation({
    mutationFn: () => notificationsService.resetTemplate(event.code, template.channel),
    onSuccess: (t) => { setSubject(t.subject ?? ""); setBody(t.body); setProviderId(""); setActive(true); toast.success("Back to the default text"); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const insert = (name: string) => {
    const el = bodyRef.current;
    const token = `{{${name}}}`;
    if (!el) { setBody((b) => b + token); return; }
    const start = el.selectionStart ?? body.length;
    const end = el.selectionEnd ?? body.length;
    const next = body.slice(0, start) + token + body.slice(end);
    setBody(next);
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
  };
  const p = preview.data;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        {template.is_custom ? <Badge variant="secondary">Customised for your clinic</Badge> : <Badge variant="outline">Platform default</Badge>}
        {hasSubject ? <Field label="Subject" htmlFor="tpl_subject"><Input id="tpl_subject" value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!canWrite} /></Field> : null}
        <Field label="Message" htmlFor="tpl_body"><Textarea id="tpl_body" ref={bodyRef} rows={template.channel === "email" ? 12 : 5} value={body} onChange={(e) => setBody(e.target.value)} disabled={!canWrite} className="font-mono text-xs" /></Field>
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">Insert a variable</p>
          <div className="flex flex-wrap gap-1.5">{event.variables.map((v) => <button key={v} type="button" disabled={!canWrite} onClick={() => insert(v)} className="rounded-md border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px] hover:bg-muted disabled:opacity-50">{v}</button>)}</div>
        </div>
        {PROVIDER_ID_HINT[template.channel] ? <Field label="Provider template id" htmlFor="tpl_pid" hint={PROVIDER_ID_HINT[template.channel]}><Input id="tpl_pid" value={providerId} onChange={(e) => setProviderId(e.target.value)} disabled={!canWrite} /></Field> : null}
        <label className="flex items-center gap-2 text-sm"><Switch checked={active} onCheckedChange={setActive} disabled={!canWrite} /> Use this custom text (off = use the default)</label>
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => save.mutate()} disabled={save.isPending || !body.trim()} data-testid="save-template">Save template</Button>
            {template.is_custom ? <Button variant="ghost" onClick={() => reset.mutate()} disabled={reset.isPending}>Reset to default</Button> : null}
          </div>
        ) : null}
      </div>
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Preview with sample data</p>
        {p?.unknown_variables.length ? <Alert variant="destructive"><AlertTriangle /><AlertDescription>Unknown variables: {p.unknown_variables.join(", ")}</AlertDescription></Alert> : null}
        {template.channel === "email" && p?.html ? (
          <iframe title="Email preview" sandbox="" srcDoc={p.html} className="h-[460px] w-full rounded-xl border bg-white" data-testid="email-preview" />
        ) : (
          <div className={template.channel === "whatsapp" ? "rounded-xl bg-[#e7f6e7] p-4 dark:bg-emerald-950/40" : "rounded-xl border bg-muted/30 p-4"} data-testid="text-preview">
            {p?.subject ? <p className="mb-1 font-medium">{p.subject}</p> : null}
            <p className="whitespace-pre-line break-words text-sm">{p?.body ?? "…"}</p>
            {p?.sms_segments ? <p className="mt-2 text-xs text-muted-foreground">{body.length > 0 ? `${p.body.length} characters · ${p.sms_segments} SMS part${p.sms_segments > 1 ? "s" : ""}` : ""}</p> : null}
          </div>
        )}
      </div>
    </div>
  );
}
