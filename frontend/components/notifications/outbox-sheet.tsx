"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { notificationsService } from "@/services/notifications";
import { useAuth } from "@/components/auth/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { CHANNEL_LABEL, NOTIFICATION_STATUS_LABEL, NOTIFICATION_STATUS_VARIANT } from "@/types/notification";

export function OutboxSheet({ id, eventLabel, onClose }: { id: string; eventLabel: (code: string) => string; onClose: () => void }) {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["notification", id], queryFn: () => notificationsService.get(id) });
  const refresh = () => ["notification", "notifications", "notification-stats"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));
  const retry = useMutation({ mutationFn: () => notificationsService.retry(id), onSuccess: () => { toast.success("Queued to send again"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const cancel = useMutation({ mutationFn: () => notificationsService.cancel(id), onSuccess: () => { toast.success("Cancelled"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const n = detail.data;
  const canWrite = hasPermission("notifications:write");
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2">{n ? eventLabel(n.event) : "Message"} {n ? <Badge variant={NOTIFICATION_STATUS_VARIANT[n.status]}>{NOTIFICATION_STATUS_LABEL[n.status]}</Badge> : null}</SheetTitle>
          <SheetDescription>{n ? `${CHANNEL_LABEL[n.channel]} to ${n.recipient_name ?? ""} ${n.recipient ?? ""}`.trim() : ""}</SheetDescription>
        </SheetHeader>
        {!n ? <Skeleton className="h-64" /> : (
          <div className="space-y-5 text-sm">
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              <div><dt className="text-muted-foreground">Created</dt><dd>{formatDateTime(n.created_at)}</dd></div>
              <div><dt className="text-muted-foreground">{n.sent_at ? "Sent" : "Due"}</dt><dd>{formatDateTime(n.sent_at ?? n.scheduled_for)}</dd></div>
              {n.appointment_reference ? <div><dt className="text-muted-foreground">Appointment</dt><dd className="font-mono text-xs">{n.appointment_reference}</dd></div> : null}
              <div><dt className="text-muted-foreground">Attempts</dt><dd>{n.attempts}</dd></div>
              {n.payload?.provider_template_id ? <div className="sm:col-span-2"><dt className="text-muted-foreground">Provider template</dt><dd className="font-mono text-xs">{n.payload.provider_template_id}</dd></div> : null}
              {n.last_error ? <div className="sm:col-span-2"><dt className="text-muted-foreground">{n.status === "cancelled" ? "Why it was not sent" : "Last error"}</dt><dd className="text-destructive">{n.last_error}</dd></div> : null}
            </dl>
            <div className="rounded-xl border bg-muted/30 p-4" data-testid="outbox-message">
              {n.subject ? <p className="mb-2 font-medium">{n.subject}</p> : null}
              <p className="whitespace-pre-line break-words">{n.body}</p>
            </div>
            {n.logs.length ? (
              <div>
                <p className="mb-2 font-medium">Delivery attempts</p>
                <ol className="space-y-1.5 text-xs">
                  {n.logs.map((l, i) => <li key={i} className="rounded-md bg-muted/40 px-2 py-1.5"><span className="font-medium">{l.status}</span> via {l.provider} · {formatDateTime(l.created_at)}{l.provider_message_id ? <span className="block break-all font-mono text-muted-foreground">{l.provider_message_id}</span> : null}{l.error ? <span className="block text-destructive">{l.error}</span> : null}</li>)}
                </ol>
              </div>
            ) : null}
            {canWrite ? (
              <div className="flex gap-2">
                {["failed", "cancelled"].includes(n.status) && n.channel !== "in_app" ? <Button onClick={() => retry.mutate()} disabled={retry.isPending}>Send again</Button> : null}
                {["pending", "scheduled"].includes(n.status) ? <Button variant="outline" onClick={() => cancel.mutate()} disabled={cancel.isPending}>Cancel message</Button> : null}
              </div>
            ) : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
