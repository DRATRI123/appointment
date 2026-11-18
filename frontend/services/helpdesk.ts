import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { Page } from "@/types/api";

export type TicketStatus = "open" | "pending_customer" | "resolved" | "closed";
export interface Person { id: string; name: string }
export interface TicketMessage {
  id: string; author_kind: "customer" | "staff" | "system"; author_name: string; internal: boolean; body: string; created_at: string;
  attachment: { name: string | null; mime: string | null; size: number | null } | null;
}
export interface Ticket {
  id: string; number: number; subject: string; category: string; category_label: string; status: TicketStatus;
  created_at: string; last_activity_at: string; resolved_at: string | null; closed_at: string | null; rating: number | null; unread: boolean;
  appointment: { reference: string; start_at: string; timezone: string; service_name: string } | null;
}
export interface TicketDetail extends Ticket { messages: TicketMessage[] }
export interface StaffTicket extends Ticket {
  priority: "low" | "normal" | "high" | "urgent"; customer: Person | null; assigned_to: Person | null; branch_name: string | null;
  first_response_due_at: string | null; first_response_at: string | null; overdue: boolean;
}
export interface StaffTicketDetail extends StaffTicket { messages: TicketMessage[] }
export interface DeskSummary {
  open: number; pending_customer: number; unassigned: number; mine: number; overdue: number; resolved_30_days: number;
  avg_first_response_hours: number | null; avg_rating: number | null;
}

function form(fields: Record<string, string | boolean | null | undefined>, file?: File | null): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null && v !== "") f.append(k, String(v));
  if (file) f.append("file", file);
  return f;
}

/** The signed-in patient's requests at one clinic (organization public id). */
export const patientHelp = {
  options: (slug: string) => api.get<{ enabled: boolean; categories: Record<string, string> }>(`/public/organizations/${slug}/help`),
  list: (orgId: string) => api.get<Ticket[]>(`/customer/organizations/${orgId}/requests`),
  get: (orgId: string, id: string) => api.get<TicketDetail>(`/customer/organizations/${orgId}/requests/${id}`),
  create: (orgId: string, body: { category: string; subject: string; body: string; appointment_reference?: string }, file?: File | null) =>
    api.post<TicketDetail>(`/customer/organizations/${orgId}/requests`, form(body, file)),
  reply: (orgId: string, id: string, body: string, file?: File | null) => api.post<TicketDetail>(`/customer/organizations/${orgId}/requests/${id}/messages`, form({ body }, file)),
  resolve: (orgId: string, id: string, rating?: number | null) => api.post<TicketDetail>(`/customer/organizations/${orgId}/requests/${id}/resolve`, { rating: rating ?? null }),
  attachmentUrl: (orgId: string, id: string, messageId: string) => `${apiBase}/customer/organizations/${orgId}/requests/${id}/messages/${messageId}/attachment`,
};

/** The clinic's help desk inbox. */
export const helpdesk = {
  summary: () => api.get<DeskSummary>("/helpdesk/summary"),
  agents: () => api.get<Person[]>("/helpdesk/agents"),
  list: (params: { status?: string; assigned?: string; category?: string; search?: string; page?: number; page_size?: number }) =>
    api.get<Page<StaffTicket>>("/helpdesk/tickets", { searchParams: params }),
  get: (id: string) => api.get<StaffTicketDetail>(`/helpdesk/tickets/${id}`),
  reply: (id: string, body: string, opts: { internal?: boolean; next_status?: "resolved" | "closed" | null }, file?: File | null) =>
    api.post<StaffTicketDetail>(`/helpdesk/tickets/${id}/messages`, form({ body, internal: opts.internal ? "true" : undefined, next_status: opts.next_status ?? undefined }, file)),
  update: (id: string, body: { status?: string; priority?: string; category?: string; assigned_to?: string; unassign?: boolean }) =>
    api.patch<StaffTicketDetail>(`/helpdesk/tickets/${id}`, body),
  attachmentUrl: (id: string, messageId: string) => `${apiBase}/helpdesk/tickets/${id}/messages/${messageId}/attachment`,
};

export const CATEGORY_LABELS: Record<string, string> = {
  booking: "Booking", reschedule_cancel: "Change or cancel", payment: "Payment", refund: "Refund",
  report: "Reports and prescription", feedback: "Feedback", other: "Something else",
};
export const STATUS_LABELS: Record<TicketStatus, string> = { open: "Waiting for clinic", pending_customer: "Waiting for you", resolved: "Solved", closed: "Closed" };
export const STAFF_STATUS_LABELS: Record<TicketStatus, string> = { open: "Open", pending_customer: "Waiting for patient", resolved: "Solved", closed: "Closed" };

/** Open a private attachment in a new tab (fetched with the session, never a public link). */
export async function openAttachment(url: string, organizationId?: string | null): Promise<void> {
  const { sessionFetch } = await import("@/lib/api-client");
  const tab = window.open("about:blank", "_blank");
  const res = await sessionFetch(url, organizationId);
  if (!res.ok) { tab?.close(); throw new Error(`Could not open the attachment (${res.status})`); }
  const objectUrl = URL.createObjectURL(await res.blob());
  if (tab) tab.location.href = objectUrl; else window.location.href = objectUrl;
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
