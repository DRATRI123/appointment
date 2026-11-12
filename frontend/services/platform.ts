import { api } from "@/lib/api-client";
import type { Page } from "@/types/api";
import type { AuditLog, Organization, PlatformStats, User } from "@/types/auth";

export const platformService = {
  stats: () => api.get<PlatformStats>("/platform/stats"),
  organizations: (params: { page?: number; page_size?: number; status?: string; search?: string }) =>
    api.get<Page<Organization>>("/platform/organizations", { searchParams: params }),
  setOrganizationStatus: (id: string, status: string, reason?: string) =>
    api.post<Organization>(`/platform/organizations/${id}/status`, { status, reason }),
  users: (params: { page?: number; page_size?: number; search?: string; status?: string }) =>
    api.get<Page<User>>("/platform/users", { searchParams: params }),
  setUserStatus: (id: string, status: string, reason?: string) => api.post<User>(`/platform/users/${id}/status`, { status, reason }),
  auditLogs: (params: { page?: number; page_size?: number }) => api.get<Page<AuditLog>>("/platform/audit-logs", { searchParams: params }),
};
