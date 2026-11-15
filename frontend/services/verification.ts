import { api } from "@/lib/api-client";

export type Channel = "sms" | "whatsapp" | "email";
export interface FieldDef { key: string; label: string; secret: boolean; required: boolean; help: string }
export interface OwnAccount {
  provider: string; enabled: boolean; settings: Record<string, string>; secrets_set: string[]; secret_hints: Record<string, string>; missing: string[];
  last_test_at: string | null; last_test_ok: boolean | null; last_test_error: string | null;
}
export interface ChannelState { channel: Channel; own: OwnAccount | null; platform: { provider: string | null; configured: boolean }; usable: boolean; using: "clinic" | "platform" | null; enabled_in_policy: boolean }
export interface OtpPolicy {
  enabled: boolean; required_for_booking: boolean; channels: Channel[]; default_channel: Channel; code_length: number; expiry_seconds: number;
  resend_cooldown_seconds: number; max_attempts: number; max_resends: number; limit_per_destination_hour: number; limit_per_ip_hour: number; limit_per_session_hour: number;
}
export interface VerificationOverview { policy: OtpPolicy; channels: ChannelState[]; providers: Record<Channel, Record<string, FieldDef[]>> }

export const verificationAdmin = {
  overview: () => api.get<VerificationOverview>("/verification"),
  savePolicy: (orgId: string, values: Partial<OtpPolicy>) => api.put<{ values: OtpPolicy }>(`/organizations/${orgId}/settings/otp`, { values }),
  saveProvider: (channel: Channel, body: { provider: string; enabled: boolean; settings: Record<string, string>; secrets: Record<string, string> }) =>
    api.put<VerificationOverview>(`/verification/providers/${channel}`, body),
  removeProvider: (channel: Channel) => api.delete<VerificationOverview>(`/verification/providers/${channel}`),
  test: (channel: Channel, destination: string) => api.post<{ ok: boolean; provider: string; source: string; error: string | null }>(`/verification/providers/${channel}/test`, { destination }),
};
