import { api } from "@/lib/api-client";
import type { User } from "@/types/auth";

export type SignInChannel = "sms" | "whatsapp" | "email";
export interface SignInOptions { channels: SignInChannel[]; default_channel: SignInChannel | null; code_length: number }
export interface SignInChallenge {
  challenge_id: string; channel: SignInChannel; destination: string; code_length: number;
  expires_in_seconds: number; resend_after_seconds: number; resends_left: number;
}

/** Patients sign in on the clinic's website with a one-time code sent through the clinic's own channels. */
export const patientSignIn = {
  options: (slug: string) => api.get<SignInOptions>(`/public/organizations/${slug}/patient-sign-in`),
  start: (slug: string, body: { channel: SignInChannel; destination: string; session_key: string }) =>
    api.post<SignInChallenge>(`/public/organizations/${slug}/patient-sign-in/start`, body),
  resend: (slug: string, challengeId: string, session_key: string) =>
    api.post<SignInChallenge>(`/public/organizations/${slug}/patient-sign-in/${challengeId}/resend`, { session_key }),
  verify: (slug: string, challengeId: string, body: { code: string; session_key: string }) =>
    api.post<{ user: User; is_new_user: boolean }>(`/public/organizations/${slug}/patient-sign-in/${challengeId}/verify`, body),
};
