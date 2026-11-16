"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Info, Plug } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { integrationsService } from "@/services/integrations";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { GoogleResult } from "@/components/integrations/google-result";
import { ProfessionalCard } from "@/components/integrations/professional-card";
import { ZoomCard } from "@/components/integrations/zoom-card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

export default function CalendarVideoPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const overview = useQuery({ queryKey: ["integrations", orgId], queryFn: integrationsService.overview, enabled: !!orgId });
  const issues = useQuery({ queryKey: ["integrations", "issues", orgId], queryFn: integrationsService.issues, enabled: !!orgId && hasPermission("integrations:read") });
  const retry = useMutation({ mutationFn: (id: number) => integrationsService.retryIssue(id), onSuccess: () => { toast.success("Queued again"); queryClient.invalidateQueries({ queryKey: ["integrations"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const o = overview.data;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <Suspense fallback={null}><GoogleResult /></Suspense>
      <Link href="/admin/integrations" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Integrations</Link>
      <PageHeader title="Calendar & video" description="Google Calendar, Google Meet and Zoom for each doctor. Appointments sync in the background, so a provider outage never blocks a booking." />
      {overview.isLoading ? <Skeleton className="h-64" /> : overview.error ? <EmptyState icon={Plug} title="No access" body={errorMessage(overview.error)} /> : o ? (
        <>
          {!o.google_configured && o.can_manage_all ? (
            <Alert variant="info"><Info /><AlertDescription>
              <span className="font-medium">Add your clinic&apos;s Google Cloud app first.</span> Calendar, Meet, Gmail, Contacts and Drive use your
              clinic&apos;s own Google app (not the platform&apos;s): <Link href="/admin/integrations/google_app" className="font-medium underline">Integrations → Google Cloud app</Link>.
              Its redirect URI is <span className="break-all font-mono text-xs">{o.google_redirect_uri}</span>.
            </AlertDescription></Alert>
          ) : null}
          {o.can_manage_all ? <ZoomCard key={o.zoom?.id ?? "none"} zoom={o.zoom} /> : null}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Professionals</h2>
            {o.professionals.length === 0 ? <EmptyState icon={Plug} title="No professionals yet" body="Add professionals first; each can connect their own calendar." /> : o.professionals.map((p) => (
              <ProfessionalCard key={`${p.professional_id}:${JSON.stringify(p.meeting)}`} row={p} googleConfigured={o.google_configured} zoomConnected={o.zoom?.status === "connected" && o.zoom.is_enabled} returnTo="/admin/integrations/calendar" />
            ))}
          </div>
          {issues.data?.length ? (
            <Card>
              <CardHeader><CardTitle>Sync problems</CardTitle><CardDescription>Calendar events or meetings that could not be created, changed or removed. They retry automatically with increasing waits.</CardDescription></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>Appointment</TableHead><TableHead>Where</TableHead><TableHead>Problem</TableHead><TableHead /></TableRow></TableHeader>
                  <TableBody>
                    {issues.data.map((i) => (
                      <TableRow key={i.id} data-testid="sync-issue">
                        <TableCell className="text-xs"><span className="font-mono">{i.appointment_reference}</span><span className="block text-muted-foreground">{formatDateTime(i.appointment_start_at)} · {i.professional_name}</span></TableCell>
                        <TableCell>{i.provider === "zoom" ? "Zoom" : "Google Calendar"}<span className="block text-xs text-muted-foreground">{i.status === "failed" ? "stopped" : `retry ${i.next_attempt_at ? formatDateTime(i.next_attempt_at) : "soon"}`} · {i.attempts} attempts</span></TableCell>
                        <TableCell className="max-w-md text-xs text-destructive">{i.last_error}</TableCell>
                        <TableCell>{hasPermission("integrations:write") ? <Button size="sm" variant="outline" onClick={() => retry.mutate(i.id)}>Retry now</Button> : null}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
