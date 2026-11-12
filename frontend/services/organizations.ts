import { api } from "@/lib/api-client";
import type { ApiErrorBody, Page } from "@/types/api";
import type { AuditLog, Domain, Member, Organization, Permission, Role, SettingsMap } from "@/types/auth";

export interface OrganizationCreateInput {
  name: string;
  slug?: string;
  business_type?: string;
  email?: string;
  phone?: string;
  timezone?: string;
  currency?: string;
}

export const organizationsService = {
  listMine: () => api.get<Organization[]>("/organizations"),
  create: (body: OrganizationCreateInput) => api.post<Organization>("/organizations", body),
  get: (id: string) => api.get<Organization>(`/organizations/${id}`),
  update: (id: string, body: Partial<Organization>) => api.patch<Organization>(`/organizations/${id}`, body),
  settings: (id: string) => api.get<SettingsMap>(`/organizations/${id}/settings`),
  updateSettings: (id: string, namespace: string, values: Record<string, unknown>) =>
    api.put<{ namespace: string; values: Record<string, unknown> }>(`/organizations/${id}/settings/${namespace}`, { values }),
  domains: (id: string) => api.get<Domain[]>(`/organizations/${id}/domains`),
  addDomain: (id: string, body: { domain: string; is_primary: boolean }) => api.post<Domain>(`/organizations/${id}/domains`, body),
  removeDomain: (id: string, domainId: number) => api.delete<ApiErrorBody>(`/organizations/${id}/domains/${domainId}`),
  members: (id: string) => api.get<Member[]>(`/organizations/${id}/members`),
  invite: (id: string, body: { identifier: string; full_name: string; role_code: string; branch_id?: string }) =>
    api.post<Member>(`/organizations/${id}/members`, body),
  updateMember: (id: string, membershipId: string, body: { role_code?: string; status?: string; clear_branch?: boolean }) =>
    api.patch<Member>(`/organizations/${id}/members/${membershipId}`, body),
  removeMember: (id: string, membershipId: string) => api.delete<ApiErrorBody>(`/organizations/${id}/members/${membershipId}`),
  roles: (id: string) => api.get<Role[]>(`/organizations/${id}/roles`),
  permissions: (id: string) => api.get<Permission[]>(`/organizations/${id}/permissions`),
  createRole: (id: string, body: { code: string; name: string; description?: string; permissions: string[]; clone_from?: string }) =>
    api.post<Role>(`/organizations/${id}/roles`, body),
  updateRole: (id: string, roleId: number, body: { name?: string; description?: string; permissions?: string[] }) =>
    api.patch<Role>(`/organizations/${id}/roles/${roleId}`, body),
  deleteRole: (id: string, roleId: number) => api.delete<ApiErrorBody>(`/organizations/${id}/roles/${roleId}`),
  auditLogs: (id: string, params: { page?: number; page_size?: number; action?: string }) =>
    api.get<Page<AuditLog>>(`/organizations/${id}/audit-logs`, { searchParams: params }),
};
