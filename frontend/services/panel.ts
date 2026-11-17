import { api } from "@/lib/api-client";
import type { PanelTokens } from "@/lib/panel-session";

export interface PanelPolicy {
  enabled: boolean;
  allowed_origins: string[];
  organization_name: string;
}

/** Embedded admin panel (the clinic's own app shows the admin panel in an iframe). */
export const panelService = {
  policy: (slug: string) => api.get<PanelPolicy>(`/panel/${slug}/policy`),
  login: (slug: string, body: { email: string; password: string; parent_origin?: string }) => api.post<PanelTokens>(`/panel/${slug}/login`, body),
  mfa: (slug: string, mfa_token: string, code: string) => api.post<PanelTokens>(`/panel/${slug}/mfa`, { mfa_token, code }),
};
