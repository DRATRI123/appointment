"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarPlus, Copy, ExternalLink, Video } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { integrationsService } from "@/services/integrations";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { downloadPrivateFile } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import type { AppointmentDetail } from "@/types/booking";

/** Staff view of an appointment's video link (set by Google Meet/Zoom sync or by hand) and a calendar file. */
export function AppointmentMeeting({ appt }: { appt: AppointmentDetail }) {
  const { hasPermission, currentOrganizationId } = useAuth();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [link, setLink] = useState(appt.meeting_link ?? "");
  const save = useMutation({
    mutationFn: (value: string | null) => integrationsService.setAppointmentLink(appt.id, value),
    onSuccess: (r) => { toast.success(r.detail); setEditing(false); ["appointment", "appointments", "calendar"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const download = useMutation({ mutationFn: () => downloadPrivateFile(integrationsService.staffIcsUrl(appt.id), `${appt.reference}.ics`, currentOrganizationId), onError: (e) => toast.error(errorMessage(e)) });
  const online = appt.consultation_mode === "online";
  const canEdit = hasPermission("appointments:write") && !["cancelled", "expired", "completed", "no_show"].includes(appt.status);
  return (
    <div className="space-y-3 rounded-xl border p-4 text-sm" data-testid="appointment-meeting">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium"><Video className="size-4" /> {online ? "Online consultation" : "In-person visit"}</p>
        <Button size="sm" variant="ghost" onClick={() => download.mutate()} disabled={download.isPending}><CalendarPlus /> Calendar file</Button>
      </div>
      {online ? (
        editing ? (
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); save.mutate(link.trim() || null); }}>
            <Input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://meet.google.com/… or https://zoom.us/j/…" aria-label="Meeting link" />
            <div className="flex gap-2"><Button type="submit" size="sm" disabled={save.isPending}>Save</Button><Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button></div>
          </form>
        ) : appt.meeting_link ? (
          <div className="flex flex-wrap items-center gap-2">
            <a href={appt.meeting_link} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 break-all text-primary underline" data-testid="meeting-link">{appt.meeting_link} <ExternalLink className="size-3.5 shrink-0" /></a>
            <Button size="icon" variant="ghost" aria-label="Copy meeting link" onClick={async () => { try { await navigator.clipboard.writeText(appt.meeting_link!); toast.success("Copied"); } catch { toast.error("Copy failed"); } }}><Copy /></Button>
            {canEdit ? <Button size="sm" variant="outline" onClick={() => setEditing(true)}>Change</Button> : null}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
            <span>{appt.status === "confirmed" ? "The video link is being created, or none is set up." : "A video link is created once the appointment is confirmed."}</span>
            {canEdit ? <Button size="sm" variant="outline" onClick={() => setEditing(true)} data-testid="add-meeting-link">Add link</Button> : null}
          </div>
        )
      ) : null}
    </div>
  );
}
