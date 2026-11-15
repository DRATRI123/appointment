import { api } from "@/lib/api-client";
import type { OTPRequestResponse, SessionInfo, TokenResponse } from "@/types/auth";
import type { ApiErrorBody } from "@/types/api";

export const authService = {
  requestOtp: (identifier: string, purpose: "login" | "register" = "login") =>
    api.post<OTPRequestResponse>("/auth/otp/request", { identifier, purpose }),
  verifyOtp: (body: { identifier: string; code: string; full_name?: string; purpose?: "login" | "register" }) =>
    api.post<TokenResponse>("/auth/otp/verify", { purpose: "login", ...body }),
  login: (body: { email: string; password: string }) => api.post<TokenResponse>("/auth/login", body),
  register: (body: { full_name: string; email: string; password: string; mobile?: string }) =>
    api.post<TokenResponse>("/auth/register", body),
  google: (id_token: string) => api.post<TokenResponse>("/auth/google", { id_token }),
  refresh: () => api.post<TokenResponse>("/auth/refresh"),
  logout: () => api.post<ApiErrorBody>("/auth/logout"),
  forgotPassword: (email: string) => api.post<ApiErrorBody>("/auth/password/forgot", { email }),
  resetPassword: (token: string, new_password: string) =>
    api.post<ApiErrorBody>("/auth/password/reset", { token, new_password }),
  changePassword: (current_password: string | null, new_password: string) =>
    api.post<ApiErrorBody>("/auth/password/change", { current_password, new_password }),
  sessions: () => api.get<SessionInfo[]>("/auth/sessions"),
  mfaVerify: (mfa_token: string, code: string) => api.post<TokenResponse>("/auth/mfa/verify", { mfa_token, code }),
  mfaStatus: () => api.get<{ enabled: boolean; enabled_at: string | null; recovery_codes_left: number }>("/auth/mfa"),
  mfaSetup: () => api.post<{ secret: string; otpauth_uri: string; qr_data_url: string }>("/auth/mfa/setup"),
  mfaEnable: (code: string) => api.post<{ recovery_codes: string[] }>("/auth/mfa/enable", { code }),
  mfaDisable: (code: string, password: string | null) => api.post<ApiErrorBody>("/auth/mfa/disable", { code, password }),
  mfaRecoveryCodes: (code: string) => api.post<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", { code }),
  revokeSession: (id: string) => api.delete<ApiErrorBody>(`/auth/sessions/${id}`),
  revokeAll: () => api.post<ApiErrorBody>("/auth/sessions/revoke-all"),
  requestEmailVerification: () => api.post<ApiErrorBody>("/auth/email/verify/request"),
  confirmEmailVerification: (token: string) => api.post<ApiErrorBody>("/auth/email/verify/confirm", { token }),
};
