import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { ApiErrorBody } from "@/types/api";
import type { Integration, IntegrationLog, IntegrationsOverview, MeetingPreference, SyncIssue } from "@/types/integration";

export const integrationsService = {
  overview: () => api.get<IntegrationsOverview>("/integrations"),
  connectGoogle: (professional_id: string, return_to: string) => api.post<{ authorization_url: string }>("/integrations/google/connect", { professional_id, return_to }),
  connectZoom: (body: { account_id: string; client_id: string; client_secret: string; default_user?: string }) => api.post<Integration>("/integrations/zoom", body),
  update: (id: string, body: Partial<{ calendar_id: string; create_meet: boolean; block_busy: boolean; show_patient_names: boolean; default_user: string; is_enabled: boolean }>) =>
    api.patch<Integration>(`/integrations/${id}`, body),
  test: (id: string) => api.post<Integration>(`/integrations/${id}/test`),
  syncNow: (id: string) => api.post<Integration>(`/integrations/${id}/sync`),
  logs: (id: string) => api.get<IntegrationLog[]>(`/integrations/${id}/logs`),
  disconnect: (id: string) => api.delete<ApiErrorBody>(`/integrations/${id}`),
  setMeeting: (professionalId: string, body: MeetingPreference) => api.put<MeetingPreference>(`/integrations/professionals/${professionalId}/meeting`, body),
  rotateFeed: (professionalId: string) => api.post<ApiErrorBody>(`/integrations/professionals/${professionalId}/feed`),
  disableFeed: (professionalId: string) => api.delete<ApiErrorBody>(`/integrations/professionals/${professionalId}/feed`),
  issues: () => api.get<SyncIssue[]>("/integrations/sync-issues"),
  retryIssue: (id: number) => api.post<ApiErrorBody>(`/integrations/sync-issues/${id}/retry`),
  setAppointmentLink: (appointmentId: string, meeting_link: string | null) => api.put<ApiErrorBody>(`/appointments/${appointmentId}/meeting`, { meeting_link }),
  staffIcsUrl: (appointmentId: string) => `${apiBase}/appointments/${appointmentId}/calendar.ics`,
  publicIcsUrl: (slug: string, reference: string, token: string | null) =>
    `${apiBase}/public/organizations/${slug}/appointments/${reference}/calendar.ics${token ? `?access_token=${encodeURIComponent(token)}` : ""}`,
};

/** "Add to Google Calendar" link for customers (no account connection needed). */
export function googleCalendarTemplateUrl(opts: { title: string; start: string; end: string; details?: string; location?: string }) {
  const fmt = (iso: string) => new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const params = new URLSearchParams({ action: "TEMPLATE", text: opts.title, dates: `${fmt(opts.start)}/${fmt(opts.end)}` });
  if (opts.details) params.set("details", opts.details);
  if (opts.location) params.set("location", opts.location);
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}
