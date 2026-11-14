"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { StatTile } from "@/components/analytics/stat-tile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { compactNumber } from "@/lib/numbers";
import { formatDateTime, timeAgo } from "@/lib/format";

const JOB_LABEL: Record<string, string> = {
  expire_holds: "Release expired slot holds",
  expire_unpaid_appointments: "Expire unpaid bookings",
  purge_expired_documents: "Delete documents past retention",
  pull_calendar_busy: "Read busy time from calendars",
  sync_external: "Sync bookings to calendars / Zoom",
  schedule_reminders: "Schedule appointment reminders",
  dispatch_notifications: "Send email, SMS and WhatsApp",
  deliver_webhooks: "Deliver webhooks",
};

const CHECK_LABEL: Record<string, string> = {
  database: "Database", migrations: "Schema migrations", storage: "Upload storage", error_tracking: "Error tracking", metrics: "Prometheus metrics",
};

function waited(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 36 * 60) return `${Math.round(minutes / 60)} h`;
  return `${Math.round(minutes / 1440)} days`;
}

function mb(bytes?: number) {
  return bytes === undefined ? "" : `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

export default function SystemHealthPage() {
  const status = useQuery({ queryKey: ["platform-system-status"], queryFn: platformService.systemStatus, refetchInterval: 30_000 });
  const s = status.data;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="System health"
        description="Background worker, scheduled jobs, waiting work and backups. Refreshes every 30 seconds."
        actions={<Button size="sm" variant="outline" onClick={() => status.refetch()} disabled={status.isFetching}><RefreshCw className={status.isFetching ? "size-4 animate-spin" : "size-4"} aria-hidden /> Refresh</Button>}
      />
      {status.isLoading || !s ? <Skeleton className="h-96" /> : (
        <>
          {s.attention.length ? (
            <Alert variant="destructive" data-testid="health-attention">
              <AlertTriangle className="size-4" aria-hidden />
              <AlertTitle>Needs attention</AlertTitle>
              <AlertDescription><ul className="list-disc space-y-1 pl-4">{s.attention.map((a) => <li key={a}>{a}</li>)}</ul></AlertDescription>
            </Alert>
          ) : (
            <Alert data-testid="health-ok"><CheckCircle2 className="size-4 text-success-ink" aria-hidden /><AlertTitle>All systems normal</AlertTitle><AlertDescription>Version {s.version} · {s.environment} · checked {timeAgo(s.checked_at)}</AlertDescription></Alert>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Background worker" value={s.worker.ok ? "Running" : "Not reporting"} hint={`Last heard ${timeAgo(s.worker.last_heartbeat_at)}${s.worker.host ? ` · ${s.worker.host}` : ""}`} />
            <StatTile label="Last backup" value={s.backup.ok ? timeAgo(s.backup.at) : s.backup.at ? "Failed" : "Never"} hint={s.backup.error ?? ([mb(s.backup.size_bytes), s.backup.encrypted ? "encrypted" : s.backup.at ? "not encrypted" : "", s.backup.offsite ? "copied off-site" : ""].filter(Boolean).join(" · ") || "Schedule the backup service")} />
            <StatTile label="Messages waiting" value={compactNumber(s.backlog.notifications_pending ?? 0)} hint={`${compactNumber(s.backlog.notifications_failed ?? 0)} failed · ${compactNumber(s.backlog.webhooks_pending ?? 0)} webhooks queued`} />
            <StatTile label="Payments to verify" value={compactNumber(s.backlog.payments_awaiting_verification ?? 0)} hint={s.backlog.payments_awaiting_verification ? `Oldest has waited ${waited(s.backlog.oldest_unverified_payment_minutes ?? 0)}` : "None waiting"} />
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">Checks</CardTitle></CardHeader>
            <CardContent>
              <ul className="grid gap-2 sm:grid-cols-2" data-testid="health-checks">
                {Object.entries(s.checks).map(([key, c]) => (
                  <li key={key} className="flex items-start gap-2 text-sm">
                    {c.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success-ink" aria-label="OK" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-destructive-ink" aria-label="Problem" />}
                    <span><span className="font-medium">{CHECK_LABEL[key] ?? key}</span><span className="block text-muted-foreground">{c.detail}</span></span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Scheduled jobs</CardTitle></CardHeader>
            <CardContent className="px-0">
              <Table className="text-sm" data-testid="health-jobs">
                <TableHeader><TableRow><TableHead className="pl-6">Job</TableHead><TableHead>Last success</TableHead><TableHead className="text-right">Duration</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="pr-6">Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {Object.keys(JOB_LABEL).map((name) => {
                    const j = s.jobs[name];
                    const failing = (j?.consecutive_failures ?? 0) > 0;
                    return (
                      <TableRow key={name}>
                        <TableCell className="pl-6"><span className="font-medium">{JOB_LABEL[name]}</span><span className="block font-mono text-xs text-muted-foreground">{name}</span></TableCell>
                        <TableCell title={j?.last_success_at ? formatDateTime(j.last_success_at) : undefined}>{timeAgo(j?.last_success_at)}</TableCell>
                        <TableCell className="text-right tabular-nums">{j?.duration_ms !== undefined ? `${j.duration_ms} ms` : "—"}</TableCell>
                        <TableCell className="text-right tabular-nums">{j?.runs ?? 0}</TableCell>
                        <TableCell className="max-w-xs pr-6">
                          {!j ? <Badge variant="outline">not run yet</Badge> : failing ? (
                            <span><Badge variant="destructive">failed {j.consecutive_failures}×</Badge><span className="mt-1 block break-words text-xs text-muted-foreground">{j.last_error}</span></span>
                          ) : <Badge variant="success">ok</Badge>}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
