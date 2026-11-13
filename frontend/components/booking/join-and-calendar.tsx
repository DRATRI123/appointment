"use client";

import { CalendarPlus, Video } from "lucide-react";
import { googleCalendarTemplateUrl, integrationsService } from "@/services/integrations";
import { Button } from "@/components/ui/button";
import type { AppointmentDetail } from "@/types/booking";

/** Customer actions: join the video consultation, add the appointment to a calendar. */
export function JoinAndCalendar({ appt, slug, token, organizationName }: { appt: AppointmentDetail; slug: string; token: string | null; organizationName: string }) {
  if (["cancelled", "expired", "no_show", "completed"].includes(appt.status)) return null;
  const online = appt.consultation_mode === "online";
  const title = `${appt.service_name} with ${appt.professional_name}`;
  const details = [`Booking ${appt.reference} at ${organizationName}`, online && appt.meeting_link ? `Join: ${appt.meeting_link}` : ""].filter(Boolean).join("\n");
  const google = googleCalendarTemplateUrl({ title, start: appt.start_at, end: appt.end_at, details, location: online ? appt.meeting_link ?? "Online" : appt.branch_name });
  return (
    <div className="flex flex-wrap gap-2" data-testid="join-and-calendar">
      {online && appt.meeting_link && appt.status === "confirmed" ? (
        <Button asChild><a href={appt.meeting_link} target="_blank" rel="noreferrer" data-testid="join-meeting"><Video /> Join video consultation</a></Button>
      ) : online && appt.status === "confirmed" ? <p className="text-sm text-muted-foreground">Your video link will appear here and be sent to you before the appointment.</p> : null}
      <Button asChild variant="outline"><a href={integrationsService.publicIcsUrl(slug, appt.reference, token)} download={`${appt.reference}.ics`}><CalendarPlus /> Add to calendar (.ics)</a></Button>
      <Button asChild variant="ghost"><a href={google} target="_blank" rel="noreferrer">Google Calendar</a></Button>
    </div>
  );
}
