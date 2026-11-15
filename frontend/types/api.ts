export interface ApiErrorBody {
  detail: string;
  code?: string;
  errors?: unknown;
  request_id?: string;
  mfa_token?: string;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface Page<T> {
  data: T[];
  meta: PageMeta;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  app: string;
  version: string;
  environment: string;
  database?: string | null;
  checks?: Record<string, string> | null;
}

export interface AppMeta {
  app: string;
  version: string;
  environment: string;
  api_prefix: string;
  currency: string;
  money_unit: string;
}

export type AppointmentStatus =
  | "draft"
  | "pending_payment"
  | "pending_verification"
  | "confirmed"
  | "checked_in"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "rescheduled"
  | "no_show"
  | "expired";

export type PaymentStatus =
  | "initiated"
  | "awaiting_payment"
  | "submitted"
  | "under_review"
  | "verified"
  | "rejected"
  | "expired"
  | "cancelled"
  | "refund_requested"
  | "refund_processed";

export type SystemRole =
  | "platform_super_admin"
  | "org_owner"
  | "org_admin"
  | "branch_manager"
  | "doctor"
  | "professional"
  | "receptionist"
  | "accountant"
  | "staff"
  | "customer";
