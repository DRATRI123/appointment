export type BusinessHours = Record<string, [string, string][]>;

export interface Branch {
  id: string;
  slug: string;
  name: string;
  code: string;
  email: string | null;
  phone: string | null;
  address: Record<string, unknown> | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string | null;
  business_hours: BusinessHours | null;
  description: string | null;
  image_url: string | null;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  image_url: string | null;
  icon: string | null;
  sort_order: number;
  is_active: boolean;
  parent_id: string | null;
  service_count: number;
}

export interface ServicePricing {
  branch_id: string;
  branch_name?: string | null;
  price_paise: number | null;
  discounted_price_paise: number | null;
  advance_amount_paise: number | null;
  is_available: boolean;
}

export type PaymentMode = "free" | "full_advance" | "partial_advance" | "pay_at_clinic" | "optional_advance";
export type ConsultationMode = "in_person" | "online" | "both";

export interface Service {
  id: string;
  slug: string;
  name: string;
  kind: "standard" | "addon" | "follow_up";
  short_description: string | null;
  description: string | null;
  image_url: string | null;
  duration_minutes: number;
  buffer_minutes: number;
  consultation_mode: ConsultationMode;
  price_paise: number;
  discounted_price_paise: number | null;
  payment_mode: PaymentMode;
  advance_amount_paise: number | null;
  advance_percent: number | null;
  tax_percent: number;
  currency: string;
  min_notice_minutes: number | null;
  max_advance_days: number | null;
  cancellation_policy: Record<string, unknown> | null;
  booking_rules: Record<string, unknown> | null;
  instructions: string | null;
  category_id: string | null;
  category_name: string | null;
  follow_up_service_id: string | null;
  follow_up_within_days: number | null;
  is_active: boolean;
  is_bookable_online: boolean;
  sort_order: number;
  pricing: ServicePricing[];
  professional_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ProfessionalBranch {
  branch_id: string;
  branch_name?: string | null;
  fee_paise: number | null;
  duration_minutes: number | null;
  buffer_minutes: number | null;
  room_label: string | null;
  is_active: boolean;
}

export interface ProfessionalServiceLink {
  service_id: string;
  service_name?: string | null;
  branch_id: string | null;
  fee_override_paise: number | null;
  duration_override_minutes: number | null;
  is_active: boolean;
}

export interface Professional {
  id: string;
  slug: string;
  display_name: string;
  title: string | null;
  profile_photo_url: string | null;
  qualification: string | null;
  specialization: string | null;
  experience_years: number | null;
  registration_number: string | null;
  registration_council: string | null;
  biography: string | null;
  languages: string[] | null;
  email: string | null;
  phone: string | null;
  consultation_modes: string[] | null;
  default_fee_paise: number | null;
  default_duration_minutes: number;
  buffer_minutes: number;
  slot_capacity: number;
  is_active: boolean;
  is_bookable_online: boolean;
  sort_order: number;
  user_id: string | null;
  branches: ProfessionalBranch[];
  services: ProfessionalServiceLink[];
  created_at: string;
  updated_at: string;
}

export interface PackageItem {
  service_id: string;
  service_name?: string | null;
  quantity: number;
}

export interface ServicePackage {
  id: string;
  name: string;
  description: string | null;
  price_paise: number;
  validity_days: number | null;
  is_active: boolean;
  items: PackageItem[];
  created_at: string;
}

export interface PublicOrganization {
  organization: import("./auth").Organization;
  branches: Branch[];
  categories: Category[];
  settings: Record<string, Record<string, unknown>>;
}
