import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";

export type ConnectionStatus = "connected" | "error" | "untested" | "not_configured" | "disabled";

export interface SettingField {
  name: string;
  env_name?: string;
  label: string;
  kind: "text" | "secret" | "choice" | "number" | "bool";
  choices: string[];
  help: string;
  when: [string, string] | null;
  required: boolean;
  source?: "panel" | "env" | "default";
  is_set: boolean;
  value?: string | number | boolean | null;
  hint?: string | null;
}

export interface TestResult {
  ok: boolean;
  message: string;
  at: string;
}

export interface PlatformSection {
  key: string;
  title: string;
  description: string;
  fields: SettingField[];
  status: ConnectionStatus;
  missing: string[];
  last_test: TestResult | null;
  restart_needed: boolean;
  docs: string;
}

export interface StorageMigration {
  status: "idle" | "queued" | "running" | "done" | "failed";
  source?: string;
  target?: string;
  total?: number;
  copied?: number;
  skipped?: number;
  failed?: number;
  bytes?: number;
  error?: string | null;
  finished_at?: string;
  switched_at?: string;
}

export interface PlatformIntegrations {
  sections: PlatformSection[];
  storage: { active: "local" | "s3"; fallback: string | null; migration: StorageMigration };
  google: { clinic_redirect_uri: string; javascript_origin: string; sign_in_enabled: boolean };
  whatsapp_webhook_url: string;
  environment: string;
  summary: { total: number; connected: number; errors: number; not_configured: number };
}

export interface StorageUsage {
  backend: string;
  public: { files: number; bytes: number };
  private: { files: number; bytes: number };
  truncated: boolean;
}

export interface SavePayload {
  values: Record<string, unknown>;
  secrets: Record<string, string>;
  clear: string[];
}

const base = "/platform/integrations";

export const platformIntegrations = {
  overview: () => api.get<PlatformIntegrations>(base),
  save: (section: string, body: SavePayload) => api.put<PlatformIntegrations>(`${base}/${section}`, body),
  test: (section: string, to?: string) => api.post<TestResult & { overview: PlatformIntegrations }>(`${base}/${section}/test`, { to: to || null }),
  switchStorage: (target: "local" | "s3") => api.post<PlatformIntegrations>(`${base}/storage/switch`, { target }),
  finishStorage: () => api.post<PlatformIntegrations>(`${base}/storage/finish`),
  usage: () => api.get<StorageUsage>(`${base}/storage/usage`),
  envUrl: (includeSecrets: boolean) => `${apiBase}${base}/env?include_secrets=${includeSecrets}`,
  whatsappTemplates: () => api.get<{ name: string; language: string; status: string; category: string }[]>(`${base}/whatsapp/templates`),
  writeEnv: () => api.post<{ path: string; written: string[]; backup: string }>(`${base}/env/write`),
};
