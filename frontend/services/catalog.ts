import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { ApiErrorBody } from "@/types/api";
import type { Branch, Category, Professional, PublicOrganization, Service, ServicePackage } from "@/types/catalog";

type Body = Record<string, unknown>;

export const catalogService = {
  // branches
  branches: (includeInactive = true) => api.get<Branch[]>("/branches", { searchParams: { include_inactive: includeInactive } }),
  createBranch: (body: Body) => api.post<Branch>("/branches", body),
  updateBranch: (id: string, body: Body) => api.patch<Branch>(`/branches/${id}`, body),
  deleteBranch: (id: string) => api.delete<ApiErrorBody>(`/branches/${id}`),
  // categories
  categories: () => api.get<Category[]>("/service-categories"),
  createCategory: (body: Body) => api.post<Category>("/service-categories", body),
  updateCategory: (id: string, body: Body) => api.patch<Category>(`/service-categories/${id}`, body),
  deleteCategory: (id: string) => api.delete<ApiErrorBody>(`/service-categories/${id}`),
  // services
  services: (params: { category_id?: string; branch_id?: string; search?: string; kind?: string } = {}) =>
    api.get<Service[]>("/services", { searchParams: params }),
  service: (id: string) => api.get<Service>(`/services/${id}`),
  createService: (body: Body) => api.post<Service>("/services", body),
  updateService: (id: string, body: Body) => api.patch<Service>(`/services/${id}`, body),
  deleteService: (id: string) => api.delete<ApiErrorBody>(`/services/${id}`),
  // packages
  packages: () => api.get<ServicePackage[]>("/service-packages"),
  createPackage: (body: Body) => api.post<ServicePackage>("/service-packages", body),
  updatePackage: (id: string, body: Body) => api.patch<ServicePackage>(`/service-packages/${id}`, body),
  deletePackage: (id: string) => api.delete<ApiErrorBody>(`/service-packages/${id}`),
  // professionals
  professionals: (params: { branch_id?: string; service_id?: string; search?: string } = {}) =>
    api.get<Professional[]>("/professionals", { searchParams: params }),
  professional: (id: string) => api.get<Professional>(`/professionals/${id}`),
  createProfessional: (body: Body) => api.post<Professional>("/professionals", body),
  updateProfessional: (id: string, body: Body) => api.patch<Professional>(`/professionals/${id}`, body),
  deleteProfessional: (id: string) => api.delete<ApiErrorBody>(`/professionals/${id}`),
  // uploads
  uploadImage: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ url: string; key: string; mime_type: string; size_bytes: number }>("/uploads/images", form);
  },
};

/** Public catalogue for the booking website (no authentication). */
export const publicCatalog = {
  organization: (slug: string) => api.get<PublicOrganization>(`/public/organizations/${slug}`),
  services: (slug: string, params: { branch_id?: string; category_id?: string } = {}) =>
    api.get<Service[]>(`/public/organizations/${slug}/services`, { searchParams: params }),
  service: (slug: string, id: string) => api.get<Service>(`/public/organizations/${slug}/services/${id}`),
  professionals: (slug: string, params: { branch_id?: string; service_id?: string } = {}) =>
    api.get<Professional[]>(`/public/organizations/${slug}/professionals`, { searchParams: params }),
  professional: (slug: string, id: string) => api.get<Professional>(`/public/organizations/${slug}/professionals/${id}`),
};

/** Absolute URL for a stored public image (the API serves /media). */
export function mediaUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("http")) return url;
  const origin = apiBase.replace(/\/api\/v1$/, "");
  return `${origin}${url}`;
}
