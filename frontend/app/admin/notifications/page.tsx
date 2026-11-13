"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { notificationsService } from "@/services/notifications";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { OutboxSheet } from "@/components/notifications/outbox-sheet";
import { ProvidersPanel } from "@/components/notifications/providers-panel";
import { SettingsPanel } from "@/components/notifications/settings-panel";
import { TemplateEditor } from "@/components/notifications/template-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";
import { CHANNEL_LABEL, NOTIFICATION_STATUS_LABEL, NOTIFICATION_STATUS_VARIANT, type Channel, type EventInfo, type NotificationStatus } from "@/types/notification";

export default function NotificationsPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const allowed = hasPermission("notifications:read");
  const [tab, setTab] = useState("outbox");
  const [status, setStatus] = useState("");
  const [channel, setChannel] = useState("");
  const [event, setEvent] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<EventInfo | null>(null);

  const stats = useQuery({ queryKey: ["notification-stats", orgId], queryFn: notificationsService.stats, enabled: !!orgId && allowed, refetchInterval: 60_000 });
  const events = useQuery({ queryKey: ["notification-events", orgId], queryFn: notificationsService.events, enabled: !!orgId && allowed });
  const templates = useQuery({ queryKey: ["notification-templates", orgId], queryFn: notificationsService.templates, enabled: !!orgId && allowed && tab === "templates" });
  const settings = useQuery({ queryKey: ["notification-settings", orgId], queryFn: notificationsService.settings, enabled: !!orgId && allowed && tab === "settings" });
  const list = useQuery({
    queryKey: ["notifications", orgId, status, channel, event, search, page],
    queryFn: () => notificationsService.list({ status: status || undefined, channel: channel || undefined, event: event || undefined, search: search || undefined, page, page_size: 25 }),
    enabled: !!orgId && allowed,
  });
  const label = (code: string) => code === "test" ? "Test message" : events.data?.find((e) => e.code === code)?.label ?? code;
  if (!allowed) return <EmptyState icon={Bell} title="No access" body="You need permission to view notifications." />;
  const s = stats.data;
  const pages = list.data ? Math.max(1, Math.ceil(list.data.meta.total / list.data.meta.page_size)) : 1;
  const cards: [string, React.ReactNode, string][] = [
    ["Sent today", s?.sent_today ?? "—", ""], ["Queued", s?.pending ?? "—", "pending"], ["Scheduled reminders", s?.scheduled ?? "—", "scheduled"], ["Failed", s?.failed ?? "—", "failed"],
  ];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Notifications" description="Booking, payment, reminder and refund messages to customers and staff, by email, SMS, WhatsApp and in-app." />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([l, v, st]) => (
          <button key={l} type="button" className="text-left" onClick={() => { setTab("outbox"); setStatus(st); setPage(1); }}>
            <Card className="gap-1 py-4 transition-colors hover:border-primary/40"><CardHeader><CardDescription>{l}</CardDescription></CardHeader><CardContent className="text-xl font-semibold">{v}</CardContent></Card>
          </button>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <div className="max-w-full overflow-x-auto">
          <TabsList>
            <TabsTrigger value="outbox">Outbox</TabsTrigger>
            <TabsTrigger value="templates">Templates</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
            <TabsTrigger value="providers">Delivery setup</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="outbox" className="space-y-4 pt-4">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Input placeholder="Search recipient, subject, appointment" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
            <NativeSelect value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} aria-label="Status"><option value="">All statuses</option>{(Object.keys(NOTIFICATION_STATUS_LABEL) as NotificationStatus[]).map((k) => <option key={k} value={k}>{NOTIFICATION_STATUS_LABEL[k]}</option>)}</NativeSelect>
            <NativeSelect value={channel} onChange={(e) => { setPage(1); setChannel(e.target.value); }} aria-label="Channel"><option value="">All channels</option>{(Object.keys(CHANNEL_LABEL) as Channel[]).map((k) => <option key={k} value={k}>{CHANNEL_LABEL[k]}</option>)}</NativeSelect>
            <NativeSelect value={event} onChange={(e) => { setPage(1); setEvent(e.target.value); }} aria-label="Message"><option value="">All messages</option>{events.data?.map((e) => <option key={e.code} value={e.code}>{e.label}</option>)}</NativeSelect>
          </div>
          {list.isLoading ? <Skeleton className="h-64" /> : list.data?.data.length === 0 ? (
            <EmptyState icon={Bell} title="No messages" body="Messages appear here as bookings, payments and reminders happen." />
          ) : (
            <>
              <Table>
                <TableHeader><TableRow><TableHead>When</TableHead><TableHead>Message</TableHead><TableHead>To</TableHead><TableHead>Channel</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {list.data?.data.map((n) => (
                    <TableRow key={n.id} className="cursor-pointer" onClick={() => setSelected(n.id)} data-testid="outbox-row">
                      <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(n.sent_at ?? n.scheduled_for ?? n.created_at)}</TableCell>
                      <TableCell className="max-w-80"><span className="block font-medium">{label(n.event)}</span><span className="block truncate text-xs text-muted-foreground">{n.subject ?? n.body}</span></TableCell>
                      <TableCell className="text-xs">{n.recipient_name}<span className="block text-muted-foreground">{n.recipient ?? (n.channel === "in_app" ? "dashboard" : "")}</span></TableCell>
                      <TableCell>{CHANNEL_LABEL[n.channel]}</TableCell>
                      <TableCell><Badge variant={NOTIFICATION_STATUS_VARIANT[n.status]}>{NOTIFICATION_STATUS_LABEL[n.status]}</Badge>{n.attempts > 1 ? <span className="block text-xs text-muted-foreground">{n.attempts} attempts</span> : null}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{list.data?.meta.total} messages</span><div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div></div>
            </>
          )}
        </TabsContent>

        <TabsContent value="templates" className="pt-4">
          {templates.isLoading || !events.data ? <Skeleton className="h-64" /> : (
            <div className="grid gap-3 md:grid-cols-2">
              {events.data.map((e) => {
                const rows = templates.data?.filter((t) => t.event === e.code) ?? [];
                const custom = rows.filter((t) => t.is_custom).map((t) => CHANNEL_LABEL[t.channel]);
                return (
                  <button key={e.code} type="button" onClick={() => setEditing(e)} className="rounded-xl border p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/30" data-testid="template-card">
                    <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{e.label}</span><Badge variant="outline">{e.audience === "staff" ? "Staff" : "Customer"}</Badge>{!e.enabled ? <Badge variant="secondary">Off</Badge> : null}</div>
                    <p className="mt-1 text-sm text-muted-foreground">{e.description}</p>
                    <p className="mt-2 text-xs text-muted-foreground">Sends by {e.channels.map((c) => CHANNEL_LABEL[c]).join(", ") || "nothing"}{custom.length ? ` · customised: ${custom.join(", ")}` : ""}</p>
                  </button>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="settings" className="pt-4">
          {settings.data && events.data ? <SettingsPanel key={JSON.stringify(settings.data)} initial={settings.data} events={events.data} /> : <Skeleton className="h-64" />}
        </TabsContent>

        <TabsContent value="providers" className="pt-4"><ProvidersPanel orgId={orgId} /></TabsContent>
      </Tabs>

      {selected ? <OutboxSheet id={selected} eventLabel={label} onClose={() => setSelected(null)} /> : null}
      {editing && templates.data ? <TemplateEditor event={editing} templates={templates.data.filter((t) => t.event === editing.code)} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}
