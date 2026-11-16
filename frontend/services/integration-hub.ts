import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { SavePayload, SettingField } from "@/services/platform-integrations";

export type HubStatus = "connected" | "active" | "error" | "untested" | "not_configured" | "not_connected" | "disabled" | "info";

export interface HubCard {
  key: string;
  name: string;
  category: string;
  description: string;
  auth?: "google" | "zoho" | "fields" | "none";
  status: HubStatus;
  enabled: boolean;
  account: string | null;
  last_synced_at: string | null;
  last_error: string | null;
  last_test: { ok: boolean; message: string; at: string } | null;
  syncs: string[];
  sync: Record<string, number>;
  docs: string;
  privacy: string;
  builtin: boolean;
  link?: string | null;
  can_manage: boolean;
}

export interface HubOverview {
  categories: { key: string; title: string }[];
  cards: HubCard[];
  summary: { total: number; connected: number; failed: number; disconnected: number };
  recent_errors: { integration: string; action: string; error: string; at: string }[];
  recent_sync: { integration: string; at: string }[];
  redirects: { google: string; zoho: string };
  google_ready: boolean;
}

export interface HubDetail extends HubCard {
  fields: SettingField[];
  scopes: string[];
  logs: { action: string; status: string; error: string | null; duration_ms: number | null; at: string }[];
  problems: { id: number; entity_type: string; entity_id: number; status: string; attempts: number; error: string | null; next_attempt_at: string | null }[];
  redirect_uri?: string;
  javascript_origin?: string;
  google_ready?: boolean;
  storage?: { active: boolean; migration: { status: string; direction?: string; total?: number; copied?: number; skipped?: number; bytes?: number; error?: string | null; finished_at?: string } };
  incoming_url?: string | null;
  actions?: Record<string, string>;
  events?: Record<string, string>;
  shown_once?: Record<string, string>;
  test?: { ok: boolean; message: string; at: string };
  queued?: number;
}

export interface FollowUpTask {
  id: string;
  title: string;
  details: string | null;
  due_at: string | null;
  status: string;
  source: string;
  created_at: string;
  customer: { id: string; name: string } | null;
}

const base = "/integrations/hub";

export const hubService = {
  overview: () => api.get<HubOverview>(base),
  detail: (key: string) => api.get<HubDetail>(`${base}/${key}`),
  save: (key: string, body: SavePayload) => api.put<HubDetail>(`${base}/${key}`, body),
  setEnabled: (key: string, enabled: boolean) => api.post<HubDetail>(`${base}/${key}/enabled`, { enabled }),
  test: (key: string, to?: string) => api.post<HubDetail>(`${base}/${key}/test`, { to: to || null }),
  connect: (key: string, returnTo: string) => api.post<{ url: string }>(`${base}/${key}/connect`, { return_to: returnTo }),
  disconnect: (key: string) => api.post<HubDetail>(`${base}/${key}/disconnect`),
  rotate: (key: string) => api.post<HubDetail>(`${base}/${key}/rotate`),
  retry: (key: string, itemId?: number) => api.post<HubDetail>(`${base}/${key}/retry`, { item_id: itemId ?? null }),
  syncAll: (key: string) => api.post<HubDetail>(`${base}/${key}/sync-all`),
  tasks: (status = "open") => api.get<FollowUpTask[]>(`${base}/tasks`, { searchParams: { status } }),
  taskDone: (id: string) => api.post<{ detail: string }>(`${base}/tasks/${id}/done`),
  storageSwitch: (on: boolean) => api.post<HubDetail>(`${base}/own_storage/switch`, { on }),
  storageUsage: () => api.get<{ where: string; files: number; bytes: number }>(`${base}/own_storage/usage`),
  tallyUrl: (from: string, to: string, includeExported: boolean) =>
    `${apiBase}${base}/tally/export?from=${from}&to=${to}&include_exported=${includeExported}`,
};
