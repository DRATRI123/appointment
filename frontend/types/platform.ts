export interface Plan {
  code: string;
  name: string;
  price_paise: number;
  billing_cycle: "monthly" | "quarterly" | "yearly";
  limits: Partial<Record<"branches" | "professionals" | "staff" | "appointments_per_month", number | null>>;
  description: string | null;
  is_active: boolean;
}

export interface PlatformSettings {
  platform_name: string;
  support_email: string;
  allow_organization_signup: boolean;
  default_plan_code: string | null;
  default_trial_days: number;
  announcement: string;
  announcement_level: "info" | "warning";
}

export interface Subscription {
  id: string;
  plan_code: string;
  plan_name: string;
  status: "trial" | "active" | "past_due" | "cancelled" | "expired";
  price_paise: number;
  billing_cycle: string;
  limits: Plan["limits"];
  starts_at: string | null;
  ends_at: string | null;
  trial_ends_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface Usage {
  branches: number;
  professionals: number;
  staff: number;
  customers: number;
  appointments_this_month: number;
  appointments_30d: number;
  verified_receipts_30d_paise: number;
}

export interface OrgSummary { id: string; name: string; slug: string; status: string; created_at: string; subscription: Subscription | null; usage: Usage; over_limit: string[] }

export interface OrgOverview extends OrgSummary {
  email: string | null;
  phone: string | null;
  timezone: string;
  owner_name: string | null;
  owner_contact: string | null;
  recent_activity: { action: string; actor: string | null; at: string }[];
}

export interface PlatformDashboard {
  days: number;
  totals: Record<string, number>;
  series: { date: string; appointments: number; signups: number }[];
  top_organizations: { id: string; name: string; appointments: number }[];
  plans: { plan: string; status: string; organizations: number }[];
}

export interface PublicPlatform { platform_name: string; support_email: string; allow_organization_signup: boolean; announcement: string; announcement_level: "info" | "warning" }

export const LIMIT_LABEL = { branches: "Branches", professionals: "Professionals", staff: "Staff", appointments_per_month: "Appointments / month" } as const;
export const SUBSCRIPTION_STATUS_LABEL: Record<Subscription["status"], string> = { trial: "Trial", active: "Active", past_due: "Past due", cancelled: "Cancelled", expired: "Expired" };
