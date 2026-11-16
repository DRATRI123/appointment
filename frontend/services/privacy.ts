import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";

export interface PrivacyPolicy {
  lock_after_minutes: number;
  lock_when_hidden: boolean;
  watermark_enabled: boolean;
  watermark_opacity: number;
  print_policy: "allow" | "warn" | "block";
  reauth_window_minutes: number;
  mask_contact_details: boolean;
  user_ref: string;
  session_ref: string;
  organization_ref: string;
  has_password: boolean;
  has_authenticator: boolean;
}

export interface RevealedContact {
  mobile: string | null;
  email: string | null;
  dependents: { id: string; mobile: string | null }[];
}

export interface StaffSession {
  id: string;
  device: string | null;
  created_at: string;
  last_seen_at: string | null;
  locked: boolean;
}

export const privacyService = {
  policy: () => api.get<PrivacyPolicy>("/users/me/privacy"),
  reauth: (body: { password?: string; code?: string; otp_code?: string }) => api.post<{ detail: string }>("/auth/reauth", body),
  sendCode: () => api.post<{ detail: string; debug_code?: string }>("/auth/reauth/send-code"),
  lock: () => api.post<{ detail: string }>("/auth/lock"),
  printAttempt: (screen: string) => api.post<{ detail: string }>("/users/me/privacy/print-attempt", { screen }),
  reveal: (customerId: string, purpose?: string) => api.post<RevealedContact>(`/customers/${customerId}/reveal`, { purpose: purpose || null }),
  documentLink: (customerId: string, documentId: string) =>
    api.post<{ url: string; expires_in: number }>(`/customers/${customerId}/documents/${documentId}/link`),
  summaryUrl: (customerId: string) => `${apiBase}/customers/${customerId}/summary.pdf`,
  memberSessions: (orgId: string, membershipId: string) => api.get<StaffSession[]>(`/organizations/${orgId}/members/${membershipId}/sessions`),
  revokeMember: (orgId: string, membershipId: string) => api.post<{ detail: string }>(`/organizations/${orgId}/members/${membershipId}/sessions/revoke`),
  revokeUser: (userId: string) => api.post<{ detail: string }>(`/platform/users/${userId}/sessions/revoke`),
};
