import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { ApiErrorBody, Page } from "@/types/api";
import type { BookingForm, Customer, CustomerDocument, CustomerNote, Dependent, FormField, FormTemplate, PublicForm } from "@/types/customer";

type Body = Record<string, unknown>;

export const customersService = {
  list: (params: { search?: string; tag?: string; segment?: string; is_guest?: boolean; page?: number; page_size?: number }) =>
    api.get<Page<Customer>>("/customers", { searchParams: params }),
  get: (id: string) => api.get<Customer>(`/customers/${id}`),
  create: (body: Body) => api.post<Customer>("/customers", body),
  update: (id: string, body: Body) => api.patch<Customer>(`/customers/${id}`, body),
  remove: (id: string) => api.delete<ApiErrorBody>(`/customers/${id}`),
  exportUrl: () => `${apiBase}/customers/export.csv`,
  dependents: (id: string) => api.get<Dependent[]>(`/customers/${id}/dependents`),
  addDependent: (id: string, body: Body) => api.post<Dependent>(`/customers/${id}/dependents`, body),
  updateDependent: (id: string, depId: string, body: Body) => api.patch<Dependent>(`/customers/${id}/dependents/${depId}`, body),
  removeDependent: (id: string, depId: string) => api.delete<ApiErrorBody>(`/customers/${id}/dependents/${depId}`),
  notes: (id: string, purpose?: string) => api.get<CustomerNote[]>(`/customers/${id}/notes`, { searchParams: { purpose } }),
  addNote: (id: string, body: Body) => api.post<CustomerNote>(`/customers/${id}/notes`, body),
  removeNote: (id: string, noteId: string) => api.delete<ApiErrorBody>(`/customers/${id}/notes/${noteId}`),
  documents: (id: string) => api.get<CustomerDocument[]>(`/customers/${id}/documents`),
  uploadDocument: (id: string, file: File, title: string, document_type: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("document_type", document_type);
    return api.post<CustomerDocument>(`/customers/${id}/documents`, form);
  },
  documentUrl: (id: string, docId: string) => `${apiBase}/customers/${id}/documents/${docId}/download`,
  removeDocument: (id: string, docId: string) => api.delete<ApiErrorBody>(`/customers/${id}/documents/${docId}`),
};

export const customerSelfService = {
  organizations: () => api.get<{ id: string; name: string; slug: string }[]>("/customer/organizations"),
  profile: (orgId: string) => api.get<Customer>(`/customer/organizations/${orgId}/profile`),
  updateProfile: (orgId: string, body: Body) => api.patch<Customer>(`/customer/organizations/${orgId}/profile`, body),
  dependents: (orgId: string) => api.get<Dependent[]>(`/customer/organizations/${orgId}/dependents`),
  addDependent: (orgId: string, body: Body) => api.post<Dependent>(`/customer/organizations/${orgId}/dependents`, body),
  updateDependent: (orgId: string, depId: string, body: Body) => api.patch<Dependent>(`/customer/organizations/${orgId}/dependents/${depId}`, body),
  removeDependent: (orgId: string, depId: string) => api.delete<ApiErrorBody>(`/customer/organizations/${orgId}/dependents/${depId}`),
};

export const formsService = {
  list: (params: { include_templates?: boolean; all_versions?: boolean } = {}) => api.get<BookingForm[]>("/booking-forms", { searchParams: params }),
  templates: () => api.get<FormTemplate[]>("/booking-forms/templates"),
  get: (id: string) => api.get<BookingForm>(`/booking-forms/${id}`),
  create: (body: Body) => api.post<BookingForm>("/booking-forms", body),
  update: (id: string, body: Body) => api.patch<BookingForm>(`/booking-forms/${id}`, body),
  publish: (id: string) => api.post<BookingForm>(`/booking-forms/${id}/publish`),
  remove: (id: string) => api.delete<ApiErrorBody>(`/booking-forms/${id}`),
  assign: (service_id: string, form_id: string | null) => api.post<ApiErrorBody>("/booking-forms/assign", { service_id, form_id }),
};

export const publicForms = {
  form: (slug: string, params: { service_id?: string; branch_id?: string }) => api.get<PublicForm | null>(`/public/organizations/${slug}/booking-form`, { searchParams: params }),
  uploadFile: (slug: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ key: string; name: string; mime_type: string; size_bytes: number }>(`/public/organizations/${slug}/booking-form-files`, form);
  },
};

/** Same visibility rule as the backend: all conditions must hold. */
export function isFieldVisible(field: FormField, answers: Record<string, unknown>): boolean {
  for (const c of field.conditions ?? []) {
    const actual = answers[c.field];
    const v = c.value;
    switch (c.operator) {
      case "equals": if (actual !== v) return false; break;
      case "not_equals": if (actual === v) return false; break;
      case "in": if (!Array.isArray(v) || !v.includes(actual)) return false; break;
      case "not_in": if (Array.isArray(v) && v.includes(actual)) return false; break;
      case "is_true": if (actual !== true) return false; break;
      case "is_false": if (actual !== false) return false; break;
      case "is_empty": if (!(actual === undefined || actual === null || actual === "" || (Array.isArray(actual) && actual.length === 0))) return false; break;
      case "is_not_empty": if (actual === undefined || actual === null || actual === "" || (Array.isArray(actual) && actual.length === 0)) return false; break;
      case "gt": if (!(Number(actual) > Number(v))) return false; break;
      case "lt": if (!(Number(actual) < Number(v))) return false; break;
    }
  }
  return true;
}
