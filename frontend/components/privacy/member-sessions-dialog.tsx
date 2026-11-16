"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { MonitorSmartphone } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { privacyService } from "@/services/privacy";

/** A staff member's signed-in devices, with "Sign out everywhere" (for a lost phone or someone leaving). */
export function MemberSessionsDialog({ orgId, membershipId, name, canRevoke }: { orgId: string; membershipId: string; name: string; canRevoke: boolean }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const sessions = useQuery({
    queryKey: ["member-sessions", orgId, membershipId],
    queryFn: () => privacyService.memberSessions(orgId, membershipId),
    enabled: open,
  });
  const revoke = useMutation({
    mutationFn: () => privacyService.revokeMember(orgId, membershipId),
    onSuccess: (r) => {
      toast.success(r.detail);
      queryClient.invalidateQueries({ queryKey: ["member-sessions", orgId, membershipId] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)} aria-label={`Devices of ${name}`} data-testid="member-devices">
        <MonitorSmartphone aria-hidden /> Devices
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Signed-in devices: {name}</DialogTitle>
            <DialogDescription>Signing out everywhere ends every session at once; they must sign in again.</DialogDescription>
          </DialogHeader>
          {sessions.isLoading ? <Skeleton className="h-24" /> : sessions.error ? (
            <p className="text-sm text-destructive">{errorMessage(sessions.error)}</p>
          ) : (sessions.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Not signed in anywhere.</p>
          ) : (
            <ul className="divide-y rounded-lg border text-sm">
              {sessions.data!.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <span>
                    <span className="font-medium">{s.device ?? "Unknown device"}</span>
                    <span className="block text-xs text-muted-foreground">Signed in {formatDateTime(s.created_at)}{s.last_seen_at ? ` · last used ${formatDateTime(s.last_seen_at)}` : ""}</span>
                  </span>
                  {s.locked ? <Badge variant="warning">locked</Badge> : null}
                </li>
              ))}
            </ul>
          )}
          {canRevoke ? (
            <DialogFooter>
              <Button variant="destructive" disabled={revoke.isPending || (sessions.data ?? []).length === 0} onClick={() => revoke.mutate()} data-testid="revoke-sessions">
                {revoke.isPending ? "Signing out…" : "Sign out everywhere"}
              </Button>
            </DialogFooter>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
