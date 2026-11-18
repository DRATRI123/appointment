"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, LifeBuoy, Settings2, Star } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/errors";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { organizationsService } from "@/services/organizations";
import { CATEGORY_LABELS, helpdesk } from "@/services/helpdesk";
import { PriorityBadge, StatusBadge } from "@/components/helpdesk/badges";

const VIEWS = [["active", "Active"], ["overdue", "Overdue"], ["open", "Waiting for clinic"], ["pending_customer", "Waiting for patient"], ["resolved", "Solved"], ["closed", "Closed"], ["all", "All"]] as const;
const ASSIGNED = [["any", "Anyone"], ["me", "Mine"], ["unassigned", "Unassigned"]] as const;

/** Admin → Help desk: patients' questions, answered by the clinic. */
export default function HelpdeskPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const [view, setView] = useState<(typeof VIEWS)[number][0]>("active");
  const [assigned, setAssigned] = useState<(typeof ASSIGNED)[number][0]>("any");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [showSettings, setShowSettings] = useState(false);
  const canRead = hasPermission("helpdesk:read");
  const summary = useQuery({ queryKey: ["desk-summary", orgId], queryFn: helpdesk.summary, enabled: !!orgId && canRead, refetchInterval: 60_000 });
  const list = useQuery({
    queryKey: ["desk-tickets", orgId, view, assigned, category, search, page],
    queryFn: () => helpdesk.list({ status: view, assigned, category: category || undefined, search: search || undefined, page, page_size: 25 }),
    enabled: !!orgId && canRead, refetchInterval: 60_000,
  });
  if (!canRead) return <EmptyState icon={LifeBuoy} title="No access" body="You need the help desk permission to see patients' requests." />;
  const s = summary.data;
  const pages = list.data ? Math.max(1, Math.ceil(list.data.meta.total / list.data.meta.page_size)) : 1;
  const cards: [string, React.ReactNode, string?][] = [
    ["Waiting for clinic", s?.open ?? "—"],
    ["Overdue", s?.overdue ?? "—", s && s.overdue > 0 ? "text-destructive" : undefined],
    ["Unassigned", s?.unassigned ?? "—"],
    ["Assigned to me", s?.mine ?? "—"],
    ["First reply (avg, 30 days)", s?.avg_first_response_hours != null ? `${s.avg_first_response_hours} h` : "—"],
    ["Patient rating", s?.avg_rating != null ? <span className="inline-flex items-center gap-1">{s.avg_rating}<Star className="size-4 fill-amber-400 text-amber-400" aria-hidden /></span> : "—"],
  ];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Help desk" description="Patients' questions about bookings, payments, refunds and reports. Answer here; patients are told and read the answer after signing in."
        actions={hasPermission("organization:write") ? <Button variant="outline" onClick={() => setShowSettings((v) => !v)}><Settings2 /> Settings</Button> : null} />
      {showSettings && orgId ? <DeskSettings orgId={orgId} /> : null}
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6" data-testid="desk-summary">
        {cards.map(([label, value, tone]) => (
          <Card key={label} className="gap-1 py-4"><CardHeader><CardDescription>{label}</CardDescription></CardHeader><CardContent className={cn("text-xl font-semibold", tone)}>{value}</CardContent></Card>
        ))}
      </div>
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div className="max-w-full overflow-x-auto"><Segmented label="Show" value={view} onChange={(v) => { setPage(1); setView(v); }} options={VIEWS} /></div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <NativeSelect aria-label="Assigned to" value={assigned} onChange={(e) => { setPage(1); setAssigned(e.target.value as typeof assigned); }} className="sm:w-36">
            {ASSIGNED.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </NativeSelect>
          <NativeSelect aria-label="Topic" value={category} onChange={(e) => { setPage(1); setCategory(e.target.value); }} className="sm:w-48">
            <option value="">All topics</option>{Object.entries(CATEGORY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </NativeSelect>
          <Input className="sm:w-64" placeholder="Search #number, title, patient" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} data-testid="desk-search" />
        </div>
      </div>
      {list.isLoading ? <Skeleton className="h-64" /> : !list.data?.data.length ? (
        <EmptyState icon={LifeBuoy} title="Nothing here" body="Patients ask questions from My bookings on your website, or from a booking's page." />
      ) : (
        <>
          <Table>
            <TableHeader><TableRow><TableHead className="w-16">#</TableHead><TableHead>Request</TableHead><TableHead>Patient</TableHead><TableHead>Status</TableHead><TableHead>Priority</TableHead><TableHead>Assigned</TableHead><TableHead className="text-right">Last activity</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.data.data.map((t) => (
                <TableRow key={t.id} data-testid="desk-row" className={cn(t.unread && "bg-primary/5")}>
                  <TableCell className="font-mono text-xs text-muted-foreground">#{t.number}</TableCell>
                  <TableCell className="max-w-md">
                    <Link href={`/admin/helpdesk/${t.id}`} className={cn("block truncate hover:underline", t.unread ? "font-semibold" : "font-medium")}>{t.subject}</Link>
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">{t.category_label}{t.branch_name ? ` · ${t.branch_name}` : ""}
                      {t.overdue ? <span className="inline-flex items-center gap-1 font-medium text-destructive"><AlertTriangle className="size-3" aria-hidden />Overdue</span> : null}</span>
                  </TableCell>
                  <TableCell>{t.customer?.name ?? "—"}</TableCell>
                  <TableCell><StatusBadge status={t.status} /></TableCell>
                  <TableCell><PriorityBadge priority={t.priority} /></TableCell>
                  <TableCell className="text-sm">{t.assigned_to?.name ?? <Badge variant="outline">Unassigned</Badge>}</TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground">{timeAgo(t.last_activity_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{list.data.meta.total} requests</span>
            <div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span>
              <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
          </div>
        </>
      )}
    </div>
  );
}

function DeskSettings({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings", orgId], queryFn: () => organizationsService.settings(orgId) });
  const saved = (settings.data?.helpdesk ?? {}) as { enabled?: boolean; first_response_hours?: number; auto_close_days?: number };
  const [draft, setDraft] = useState<{ enabled: boolean; first_response_hours: number; auto_close_days: number } | null>(null);
  const value = draft ?? { enabled: saved.enabled !== false, first_response_hours: saved.first_response_hours ?? 24, auto_close_days: saved.auto_close_days ?? 7 };
  const save = useMutation({
    mutationFn: () => organizationsService.updateSettings(orgId, "helpdesk", value),
    onSuccess: () => { toast.success("Help desk settings saved"); setDraft(null); void queryClient.invalidateQueries({ queryKey: ["settings", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (settings.isLoading) return <Skeleton className="h-40" />;
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Help desk settings</CardTitle><CardDescription>Applies to this clinic.</CardDescription></CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-3">
        <label className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"><span>Patients can ask questions online</span>
          <Switch checked={value.enabled} onCheckedChange={(v) => setDraft({ ...value, enabled: v })} /></label>
        <div className="space-y-1"><Label htmlFor="hd_first">First reply target (hours)</Label>
          <Input id="hd_first" type="number" min={1} max={168} value={value.first_response_hours} onChange={(e) => setDraft({ ...value, first_response_hours: Number(e.target.value) })} /></div>
        <div className="space-y-1"><Label htmlFor="hd_close">Close solved requests after (days)</Label>
          <Input id="hd_close" type="number" min={1} max={60} value={value.auto_close_days} onChange={(e) => setDraft({ ...value, auto_close_days: Number(e.target.value) })} /></div>
        <div className="sm:col-span-3 flex justify-end"><Button onClick={() => save.mutate()} disabled={!draft || save.isPending}>Save</Button></div>
      </CardContent>
    </Card>
  );
}
