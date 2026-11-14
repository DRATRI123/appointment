import { api } from "@/lib/api-client";
import type { Page } from "@/types/api";
import { apiBase } from "@/lib/env";
import type { AuditLog, Organization, PlatformStats, User } from "@/types/auth";
import type { OrgOverview, OrgSummary, Plan, PlatformDashboard, PlatformSettings, PublicPlatform, Subscription } from "@/types/platform";

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
  dashboard: (days = 30) => api.get<PlatformDashboard>("/platform/dashboard", { searchParams: { days } }),
  settings: () => api.get<PlatformSettings>("/platform/settings"),
  saveSettings: (body: PlatformSettings) => api.put<PlatformSettings>("/platform/settings", body),
  plans: () => api.get<Plan[]>("/platform/plans"),
  savePlans: (body: Plan[]) => api.put<Plan[]>("/platform/plans", body),
  subscriptions: (params: { search?: string; plan?: string; status?: string; over_limit?: boolean } = {}) => api.get<OrgSummary[]>("/platform/subscriptions", { searchParams: params }),
  overview: (id: string) => api.get<OrgOverview>(`/platform/organizations/${id}/overview`),
  history: (id: string) => api.get<Subscription[]>(`/platform/organizations/${id}/subscriptions`),
  setSubscription: (id: string, body: { plan_code: string; status: string; trial_ends_at?: string | null; ends_at?: string | null; price_paise?: number | null; notes?: string | null }) =>
    api.put<OrgSummary>(`/platform/organizations/${id}/subscription`, body),
  exportUrl: (format: "csv" | "xlsx") => `${apiBase}/platform/exports/organizations?format=${format}`,
  publicInfo: () => api.get<PublicPlatform>("/meta/platform"),
};
