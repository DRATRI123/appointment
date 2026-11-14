import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { AnalyticsFilters, Dashboard, ReportInfo, ReportResult } from "@/types/analytics";

const clean = (f: AnalyticsFilters) => Object.fromEntries(Object.entries(f).filter(([, v]) => v)) as Record<string, string>;

export const analyticsService = {
  dashboard: (f: AnalyticsFilters, mine = false) => api.get<Dashboard>("/analytics/dashboard", { searchParams: { ...clean(f), mine: mine || undefined } }),
  reports: () => api.get<ReportInfo[]>("/reports"),
  report: (key: string, f: AnalyticsFilters & { page?: number; page_size?: number }) => api.get<ReportResult>(`/reports/${key}`, { searchParams: clean(f as AnalyticsFilters) }),
  exportUrl: (key: string, f: AnalyticsFilters, format: "csv" | "xlsx") =>
    `${apiBase}/reports/${key}/export?${new URLSearchParams({ ...clean(f), format }).toString()}`,
};
