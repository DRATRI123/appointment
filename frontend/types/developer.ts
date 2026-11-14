export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  allowed_ips: string[];
  rate_limit_per_minute: number;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
  created_by_name: string | null;
  created_at: string;
  requests_30d: number;
}
export interface ApiKeyCreated extends ApiKey { key: string }
export interface ScopeInfo { code: string; description: string; you_have_it: boolean }

export interface WebhookEndpoint {
  id: string;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  api_version: string;
  failure_count: number;
  disabled_at: string | null;
  created_at: string;
  delivered_7d: number;
  failed_7d: number;
}
export interface WebhookCreated extends WebhookEndpoint { secret: string }

export interface Delivery {
  id: string;
  event_id: string;
  event: string;
  status: "pending" | "retrying" | "delivered" | "failed" | "dead" | "sending";
  attempts: number;
  response_status: number | null;
  last_error: string | null;
  next_attempt_at: string | null;
  last_attempt_at: string | null;
  created_at: string;
}
export interface DeliveryDetail extends Delivery { payload: Record<string, unknown>; response_body: string | null }
export interface EventInfo { name: string; description: string; sample: Record<string, unknown> }
export interface UsageDay { day: string; requests: number; client_errors: number; server_errors: number; rate_limited: number }
export interface OrgApiUsage {
  organization_id: string;
  organization_name: string;
  active_keys: number;
  requests: number;
  errors: number;
  rate_limited: number;
  endpoints: number;
  endpoints_disabled: number;
  deliveries_ok: number;
  deliveries_failed: number;
}

export const DELIVERY_VARIANT: Record<Delivery["status"], "success" | "warning" | "destructive" | "outline" | "secondary"> = {
  delivered: "success", pending: "secondary", sending: "secondary", retrying: "warning", failed: "destructive", dead: "destructive",
};
