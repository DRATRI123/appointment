import { api } from "@/lib/api-client";
import type { ApiErrorBody, Page } from "@/types/api";
import type {
  EventInfo, Inbox, MessagePreferences, NotificationDetail, NotificationItem, NotificationSettings, NotificationStats, NotificationTemplate, ProviderStatus, TemplatePreview,
} from "@/types/notification";

export const notificationsService = {
  list: (params: { status?: string; channel?: string; event?: string; search?: string; page?: number; page_size?: number }) =>
    api.get<Page<NotificationItem>>("/notifications", { searchParams: params }),
  get: (id: string) => api.get<NotificationDetail>(`/notifications/${id}`),
  stats: () => api.get<NotificationStats>("/notifications/stats"),
  retry: (id: string) => api.post<NotificationDetail>(`/notifications/${id}/retry`),
  cancel: (id: string) => api.post<NotificationDetail>(`/notifications/${id}/cancel`),
  providers: () => api.get<ProviderStatus[]>("/notifications/providers"),
  events: () => api.get<EventInfo[]>("/notifications/events"),
  templates: () => api.get<NotificationTemplate[]>("/notifications/templates"),
  saveTemplate: (event: string, channel: string, body: { subject?: string | null; body: string; provider_template_id?: string | null; is_active?: boolean }) =>
    api.put<NotificationTemplate>(`/notifications/templates/${event}/${channel}`, body),
  resetTemplate: (event: string, channel: string) => api.delete<NotificationTemplate>(`/notifications/templates/${event}/${channel}`),
  preview: (event: string, channel: string, body: { subject?: string | null; body: string }) => api.post<TemplatePreview>(`/notifications/templates/${event}/${channel}/preview`, body),
  settings: () => api.get<NotificationSettings>("/notifications/settings"),
  saveSettings: (body: NotificationSettings) => api.put<NotificationSettings>("/notifications/settings", body),
  test: (channel: string, to: string) => api.post<NotificationDetail>("/notifications/test", { channel, to }),
};

export const inboxService = {
  mine: (unreadOnly = false) => api.get<Inbox>("/me/notifications", { searchParams: { unread_only: unreadOnly || undefined } }),
  markRead: (ids?: string[]) => api.post<ApiErrorBody>("/me/notifications/read", { ids: ids ?? null }),
};

export const preferencesService = {
  list: () => api.get<MessagePreferences[]>("/customer/notification-preferences"),
  update: (organizationId: string, body: Partial<Pick<MessagePreferences, "email" | "sms" | "whatsapp" | "reminders">>) =>
    api.patch<MessagePreferences>(`/customer/notification-preferences/${organizationId}`, body),
};
