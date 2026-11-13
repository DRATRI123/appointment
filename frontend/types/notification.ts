export type Channel = "email" | "sms" | "whatsapp" | "in_app";
export type NotificationStatus = "pending" | "scheduled" | "sending" | "sent" | "failed" | "cancelled" | "read";

export interface EventInfo {
  code: string;
  label: string;
  audience: "customer" | "staff";
  description: string;
  variables: string[];
  default_channels: Channel[];
  enabled: boolean;
  channels: Channel[];
}

export interface NotificationTemplate {
  event: string;
  channel: Channel;
  subject: string | null;
  body: string;
  provider_template_id: string | null;
  is_custom: boolean;
  is_active: boolean;
  default_subject: string | null;
  default_body: string;
  updated_at: string | null;
}

export interface TemplatePreview { subject: string | null; body: string; html: string | null; sms_segments: number | null; unknown_variables: string[] }

export interface NotificationItem {
  id: string;
  event: string;
  channel: Channel;
  status: NotificationStatus;
  recipient: string | null;
  recipient_name: string | null;
  subject: string | null;
  body: string;
  scheduled_for: string | null;
  sent_at: string | null;
  read_at: string | null;
  attempts: number;
  last_error: string | null;
  appointment_reference: string | null;
  created_at: string;
}

export interface NotificationDetail extends NotificationItem {
  logs: { provider: string; provider_message_id: string | null; status: string; error: string | null; created_at: string }[];
  payload: { provider_template_id?: string | null; template_params?: string[]; link?: string | null } | null;
}

export interface NotificationStats { sent_today: number; failed: number; scheduled: number; pending: number }

export interface ProviderStatus { channel: "email" | "sms" | "whatsapp"; provider: string | null; configured: boolean; is_console: boolean; error: string | null; enabled_for_organization: boolean }

export interface NotificationSettings {
  email_enabled: boolean;
  sms_enabled: boolean;
  whatsapp_enabled: boolean;
  in_app_enabled: boolean;
  notify_staff_on_booking: boolean;
  reminder_hours: number[];
  reply_to_email: string;
  events: Record<string, { enabled: boolean; channels: Channel[] }>;
}

export interface InboxItem { id: string; event: string; title: string | null; body: string; link: string | null; organization_id: string | null; read_at: string | null; created_at: string }
export interface Inbox { items: InboxItem[]; unread: number }

export interface MessagePreferences {
  email: boolean;
  sms: boolean;
  whatsapp: boolean;
  reminders: boolean;
  organization_id: string;
  organization_name: string;
  whatsapp_available: boolean;
}

export const CHANNEL_LABEL: Record<Channel, string> = { email: "Email", sms: "SMS", whatsapp: "WhatsApp", in_app: "In-app" };
export const NOTIFICATION_STATUS_LABEL: Record<NotificationStatus, string> = {
  pending: "Queued", scheduled: "Scheduled", sending: "Sending", sent: "Sent", failed: "Failed", cancelled: "Cancelled", read: "Read",
};
export const NOTIFICATION_STATUS_VARIANT: Record<NotificationStatus, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  pending: "warning", scheduled: "secondary", sending: "warning", sent: "success", failed: "destructive", cancelled: "outline", read: "success",
};
