import { api } from "@/lib/api-client";
import type { Page } from "@/types/api";
import type { ApiKey, ApiKeyCreated, Delivery, DeliveryDetail, EventInfo, OrgApiUsage, ScopeInfo, UsageDay, WebhookCreated, WebhookEndpoint } from "@/types/developer";

export const developersService = {
  scopes: () => api.get<ScopeInfo[]>("/developers/scopes"),
  keys: () => api.get<ApiKey[]>("/developers/api-keys"),
  createKey: (body: { name: string; scopes: string[]; expires_at?: string | null; allowed_ips?: string[]; rate_limit_per_minute?: number | null }) => api.post<ApiKeyCreated>("/developers/api-keys", body),
  revokeKey: (id: string) => api.delete<ApiKey>(`/developers/api-keys/${id}`),
  rotateKey: (id: string, graceHours = 24) => api.post<ApiKeyCreated>(`/developers/api-keys/${id}/rotate?grace_hours=${graceHours}`),
  accessLogs: (id: string) => api.get<{ method: string; path: string; status: number; duration_ms: number | null; ip: string | null; at: string }[]>(`/developers/api-keys/${id}/access-logs`),
  usage: (id: string, days = 30) => api.get<UsageDay[]>(`/developers/api-keys/${id}/usage`, { searchParams: { days } }),
  events: () => api.get<EventInfo[]>("/developers/events"),
  webhooks: () => api.get<WebhookEndpoint[]>("/developers/webhooks"),
  createWebhook: (body: { name: string; url: string; events: string[] }) => api.post<WebhookCreated>("/developers/webhooks", body),
  updateWebhook: (id: string, body: Partial<{ name: string; url: string; events: string[]; is_active: boolean }>) => api.patch<WebhookEndpoint>(`/developers/webhooks/${id}`, body),
  deleteWebhook: (id: string) => api.delete<{ detail: string }>(`/developers/webhooks/${id}`),
  rotateSecret: (id: string) => api.post<{ detail: string }>(`/developers/webhooks/${id}/rotate-secret`),
  test: (id: string) => api.post<DeliveryDetail>(`/developers/webhooks/${id}/test`),
  deliveries: (id: string, params: { status?: string; page?: number; page_size?: number } = {}) => api.get<Page<Delivery>>(`/developers/webhooks/${id}/deliveries`, { searchParams: params }),
  delivery: (id: string) => api.get<DeliveryDetail>(`/developers/deliveries/${id}`),
  redeliver: (id: string) => api.post<Delivery>(`/developers/deliveries/${id}/redeliver`),
  platformUsage: (days = 30) => api.get<OrgApiUsage[]>("/platform/api-usage", { searchParams: { days } }),
};
