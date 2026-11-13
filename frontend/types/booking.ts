export interface ScheduleWindow {
  weekday: number;
  start_time: string;
  end_time: string;
  slot_minutes: number | null;
  capacity: number;
  consultation_mode: string | null;
  valid_from: string | null;
  valid_to: string | null;
}

export interface Schedule extends ScheduleWindow {
  id: number;
  professional_id: string;
  branch_id: string;
  is_active: boolean;
}

export interface ScheduleException {
  id: number;
  professional_id: string;
  branch_id: string | null;
  date: string;
  is_available: boolean;
  start_time: string | null;
  end_time: string | null;
  capacity: number | null;
  reason: string | null;
}

export interface Holiday {
  id: number;
  branch_id: string | null;
  date: string;
  name: string;
  is_recurring_yearly: boolean;
}

export interface Leave {
  id: string;
  professional_id: string;
  branch_id: string | null;
  leave_type: string;
  start_at: string;
  end_at: string;
  reason: string | null;
  status: string;
}

export interface Slot {
  start_at: string;
  end_at: string;
  remaining: number;
  professional_id: string;
}

export interface DayAvailability {
  date: string;
  timezone: string;
  service_id: string;
  branch_id: string;
  duration_minutes: number;
  professionals: { professional_id: string; display_name: string; slots: Slot[] }[];
}

export interface AvailabilitySummary {
  date: string;
  available: boolean;
  slot_count: number;
}

export interface Hold {
  id: string;
  professional_id: string;
  branch_id: string;
  service_id: string;
  start_at: string;
  end_at: string;
  expires_at: string;
  session_key: string;
  status: string;
}

export interface PriceQuote {
  currency: string;
  subtotal_paise: number;
  discount_paise: number;
  tax_paise: number;
  total_amount_paise: number;
  advance_due_paise: number;
  payment_mode: string;
  breakdown: Record<string, unknown>;
}

export type AppointmentStatus =
  | "draft" | "pending_payment" | "pending_verification" | "confirmed" | "checked_in" | "in_progress"
  | "completed" | "cancelled" | "rescheduled" | "no_show" | "expired";

export interface CustomerSummary {
  id: string;
  full_name: string;
  mobile: string | null;
  email: string | null;
  is_guest: boolean;
}

export interface Appointment {
  id: string;
  reference: string;
  status: AppointmentStatus;
  source: string;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  branch_id: string;
  branch_name: string;
  professional_id: string;
  professional_name: string;
  service_id: string;
  service_name: string;
  customer: CustomerSummary;
  dependent_id: string | null;
  start_at: string;
  end_at: string;
  timezone: string;
  consultation_mode: string;
  currency: string;
  subtotal_paise: number;
  discount_paise: number;
  tax_paise: number;
  total_amount_paise: number;
  advance_due_paise: number;
  paid_amount_paise: number;
  payment_due_at: string | null;
  customer_notes: string | null;
  internal_notes: string | null;
  meeting_link: string | null;
  is_follow_up: boolean;
  recurrence_group_id: string | null;
  parent_appointment_id: string | null;
  confirmed_at: string | null;
  checked_in_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  can_cancel: boolean;
  can_reschedule: boolean;
  access_token: string | null;
}

export interface AppointmentDetail extends Appointment {
  history: { from_status: string | null; to_status: string; changed_at: string; reason: string | null; changed_by: string | null }[];
  pricing_snapshot: Record<string, unknown> | null;
  form_answers: Record<string, unknown> | null;
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  status: AppointmentStatus;
  professional_id: string;
  professional_name: string;
  branch_id: string;
  service_name: string;
  customer_name: string;
  reference: string;
}

export interface WaitlistEntry {
  id: string;
  customer: CustomerSummary;
  branch_id: string | null;
  professional_id: string | null;
  service_id: string | null;
  preferred_date: string | null;
  status: string;
  notes: string | null;
  created_at: string;
}

export const STATUS_LABEL: Record<AppointmentStatus, string> = {
  draft: "Draft", pending_payment: "Pending payment", pending_verification: "Verifying payment", confirmed: "Confirmed", checked_in: "Checked in",
  in_progress: "In progress", completed: "Completed", cancelled: "Cancelled", rescheduled: "Rescheduled", no_show: "No show", expired: "Expired",
};

export const STATUS_VARIANT: Record<AppointmentStatus, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  draft: "outline", pending_payment: "warning", pending_verification: "warning", confirmed: "success", checked_in: "secondary", in_progress: "secondary",
  completed: "default", cancelled: "destructive", rescheduled: "secondary", no_show: "destructive", expired: "outline",
};
