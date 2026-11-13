export interface CustomerStats {
  total_appointments: number;
  upcoming_appointments: number;
  completed_appointments: number;
  cancelled_appointments: number;
  no_shows: number;
  total_paid_paise: number;
  last_visit_at: string | null;
  next_appointment_at: string | null;
}

export interface Customer {
  id: string;
  customer_code: string | null;
  user_id: string | null;
  full_name: string;
  mobile: string | null;
  email: string | null;
  date_of_birth: string | null;
  gender: string | null;
  address: Record<string, string> | null;
  profile_photo_url: string | null;
  blood_group: string | null;
  communication_preferences: Record<string, boolean> | null;
  consent: Record<string, boolean> | null;
  tags: string[];
  is_guest: boolean;
  source: string | null;
  registered_at: string | null;
  last_visit_at: string | null;
  saved_professional_ids: string[];
  saved_branch_ids: string[];
  created_at: string;
  stats: CustomerStats | null;
  dependents_count: number;
}

export interface Dependent {
  id: string;
  customer_id: string;
  full_name: string;
  relationship_label: string | null;
  date_of_birth: string | null;
  gender: string | null;
  mobile: string | null;
  notes: string | null;
  created_at: string;
}

export interface CustomerNote {
  id: string;
  note_type: string;
  body: string;
  is_sensitive: boolean;
  appointment_id: string | null;
  author_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerDocument {
  id: string;
  title: string;
  document_type: string;
  mime_type: string;
  size_bytes: number;
  is_sensitive: boolean;
  appointment_id: string | null;
  uploaded_by_name: string | null;
  retention_until: string | null;
  created_at: string;
}

export type FieldType = "text" | "textarea" | "number" | "email" | "mobile" | "dropdown" | "radio" | "checkbox" | "date" | "file" | "multi_select";

export interface FieldOption { value: string; label: string }
export interface FieldCondition { field: string; operator: string; value?: unknown }
export interface FieldValidation {
  min_length?: number | null; max_length?: number | null; min?: number | null; max?: number | null; regex?: string | null; regex_message?: string | null;
  max_files?: number | null; accept?: string[] | null; min_date?: string | null; max_date?: string | null;
}

export interface FormField {
  id?: string;
  key: string;
  label: string;
  field_type: FieldType;
  placeholder: string | null;
  help_text: string | null;
  is_required: boolean;
  sort_order: number;
  options: FieldOption[] | null;
  validation: FieldValidation | null;
  conditions: FieldCondition[] | null;
  default_value: unknown;
  is_sensitive: boolean;
}

export interface BookingForm {
  id: string;
  slug: string;
  name: string;
  version: number;
  description: string | null;
  instructions: string | null;
  scope: "organization" | "branch" | "service";
  branch_id: string | null;
  settings: Record<string, unknown> | null;
  is_template: boolean;
  is_published: boolean;
  is_active: boolean;
  fields: FormField[];
  service_count: number;
  response_count: number;
  created_at: string;
  updated_at: string;
}

export interface PublicForm {
  id: string;
  name: string;
  version: number;
  description: string | null;
  instructions: string | null;
  fields: FormField[];
}

export interface FormTemplate { name: string; slug: string; description: string; fields: Partial<FormField>[] }

export const FIELD_TYPE_LABEL: Record<FieldType, string> = {
  text: "Short text", textarea: "Paragraph", number: "Number", email: "Email", mobile: "Mobile number", dropdown: "Dropdown", radio: "Single choice",
  checkbox: "Checkbox", date: "Date", file: "File upload", multi_select: "Multiple choice",
};
