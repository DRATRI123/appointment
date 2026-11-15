import { api } from "@/lib/api-client";
import type { ApiErrorBody } from "@/types/api";
import type {
  Appointment,
  AppointmentDetail,
  AvailabilitySummary,
  CalendarEvent,
  DayAvailability,
  Hold,
  Holiday,
  Leave,
  PriceQuote,
  Schedule,
  ScheduleException,
  ScheduleWindow,
  WaitlistEntry,
} from "@/types/booking";

type Body = Record<string, unknown>;

export const schedulingService = {
  schedules: (params: { professional_id?: string; branch_id?: string } = {}) => api.get<Schedule[]>("/schedules", { searchParams: params }),
  setSchedule: (professional_id: string, branch_id: string, windows: ScheduleWindow[]) => api.put<Schedule[]>("/schedules", { professional_id, branch_id, windows }),
  exceptions: (params: { professional_id?: string; from_date?: string; to_date?: string } = {}) => api.get<ScheduleException[]>("/schedules/exceptions", { searchParams: params }),
  addException: (body: Body) => api.post<ScheduleException>("/schedules/exceptions", body),
  deleteException: (id: number) => api.delete<ApiErrorBody>(`/schedules/exceptions/${id}`),
  holidays: () => api.get<Holiday[]>("/schedules/holidays"),
  addHoliday: (body: Body) => api.post<Holiday>("/schedules/holidays", body),
  deleteHoliday: (id: number) => api.delete<ApiErrorBody>(`/schedules/holidays/${id}`),
  leaves: (params: { professional_id?: string } = {}) => api.get<Leave[]>("/schedules/leaves", { searchParams: params }),
  addLeave: (body: Body) => api.post<Leave>("/schedules/leaves", body),
  deleteLeave: (id: string) => api.delete<ApiErrorBody>(`/schedules/leaves/${id}`),
  availability: (params: { service_id: string; branch_id: string; date: string; professional_id?: string }) => api.get<DayAvailability>("/availability", { searchParams: params }),
  summary: (params: { service_id: string; branch_id: string; from_date: string; to_date: string; professional_id?: string }) => api.get<AvailabilitySummary[]>("/availability/summary", { searchParams: params }),
};

export const appointmentsService = {
  list: (params: Body = {}) => api.get<Appointment[]>("/appointments", { searchParams: params as Record<string, string> }),
  calendar: (params: { from_at: string; to_at: string; professional_id?: string; branch_id?: string }) => api.get<CalendarEvent[]>("/appointments/calendar", { searchParams: params }),
  get: (id: string) => api.get<AppointmentDetail>(`/appointments/${id}`),
  create: (body: Body) => api.post<AppointmentDetail>("/appointments", body),
  createRecurring: (body: Body) => api.post<{ recurrence_group_id: string; created: Appointment[]; skipped: { start_at: string; reason: string }[] }>("/appointments/recurring", body),
  status: (id: string, action: string, reason?: string) => api.post<AppointmentDetail>(`/appointments/${id}/status`, { action, reason }),
  reschedule: (id: string, body: Body) => api.post<AppointmentDetail>(`/appointments/${id}/reschedule`, body),
  hold: (body: Body) => api.post<Hold>("/appointments/holds", body),
  releaseHold: (id: string) => api.delete<ApiErrorBody>(`/appointments/holds/${id}`),
  waitlist: () => api.get<WaitlistEntry[]>("/waitlist"),
  addWaitlist: (body: Body) => api.post<WaitlistEntry>("/waitlist", body),
  removeWaitlist: (id: string) => api.delete<ApiErrorBody>(`/waitlist/${id}`),
};

export const customerBooking = {
  mine: () => api.get<Appointment[]>("/customer/appointments"),
  get: (id: string) => api.get<AppointmentDetail>(`/customer/appointments/${id}`),
  cancel: (id: string, reason?: string) => api.post<AppointmentDetail>(`/customer/appointments/${id}/cancel`, { action: "cancel", reason }),
  reschedule: (id: string, hold_id: string, reason?: string) => api.post<AppointmentDetail>(`/customer/appointments/${id}/reschedule`, { hold_id, reason }),
};

export const publicBooking = {
  availability: (slug: string, params: { service_id: string; branch_id: string; date: string; professional_id?: string }) =>
    api.get<DayAvailability>(`/public/organizations/${slug}/availability`, { searchParams: params }),
  summary: (slug: string, params: { service_id: string; branch_id: string; from_date: string; to_date: string; professional_id?: string }) =>
    api.get<AvailabilitySummary[]>(`/public/organizations/${slug}/availability/summary`, { searchParams: params }),
  quote: (slug: string, params: { service_id: string; branch_id: string; professional_id?: string; coupon_code?: string }) => api.get<PriceQuote>(`/public/organizations/${slug}/quote`, { searchParams: params }),
  hold: (slug: string, body: Body) => api.post<Hold>(`/public/organizations/${slug}/holds`, body),
  releaseHold: (slug: string, id: string, session_key: string) => api.delete<ApiErrorBody>(`/public/organizations/${slug}/holds/${id}`, { searchParams: { session_key } }),
  /** `idempotencyKey`: the same key for every retry of one booking, so a double tap or a retried request never books twice. */
  book: (slug: string, body: Body, idempotencyKey?: string) =>
    api.post<AppointmentDetail>(`/public/organizations/${slug}/appointments`, body, idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : undefined),
  verificationOptions: (slug: string) => api.get<VerificationOptions>(`/public/organizations/${slug}/verification`),
  startVerification: (slug: string, body: { channel: VerificationChannel; destination: string; hold_id: string; session_key: string }) =>
    api.post<VerificationChallenge>(`/public/organizations/${slug}/verification/start`, body),
  resendVerification: (slug: string, challengeId: string, session_key: string) =>
    api.post<VerificationChallenge>(`/public/organizations/${slug}/verification/${challengeId}/resend`, { session_key }),
  verifyCode: (slug: string, challengeId: string, body: { code: string; session_key: string }) =>
    api.post<{ verification_token: string; channel: VerificationChannel; destination: string; expires_in_seconds: number }>(`/public/organizations/${slug}/verification/${challengeId}/verify`, body),
  status: (slug: string, reference: string, access_token?: string | null) =>
    api.get<AppointmentDetail>(`/public/organizations/${slug}/appointments/${reference}`, { searchParams: { access_token: access_token ?? undefined } }),
  cancel: (slug: string, reference: string, access_token: string | null, reason?: string) =>
    api.post<AppointmentDetail>(`/public/organizations/${slug}/appointments/${reference}/cancel`, { action: "cancel", reason }, { searchParams: { access_token: access_token ?? undefined } }),
  reschedule: (slug: string, reference: string, access_token: string | null, hold_id: string, session_key: string) =>
    api.post<AppointmentDetail>(`/public/organizations/${slug}/appointments/${reference}/reschedule`, { hold_id }, { searchParams: { access_token: access_token ?? undefined, session_key } }),
};

/** Stable per-browser key used to own slot holds. */
export function bookingSessionKey(): string {
  const KEY = "ap.bookingSession";
  try {
    let v = window.sessionStorage.getItem(KEY);
    if (!v) {
      v = crypto.randomUUID();
      window.sessionStorage.setItem(KEY, v);
    }
    return v;
  } catch {
    return `anon-${Math.random().toString(36).slice(2)}`;
  }
}

export type VerificationChannel = "sms" | "whatsapp" | "email";
export interface VerificationOptions { required: boolean; channels: VerificationChannel[]; default_channel: VerificationChannel | null; code_length: number; resend_cooldown_seconds: number }
export interface VerificationChallenge { challenge_id: string; channel: VerificationChannel; destination: string; code_length: number; expires_in_seconds: number; resend_after_seconds: number; resends_left: number }
