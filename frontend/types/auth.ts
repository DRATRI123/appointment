import type { Page } from "./api";

export interface User {
  id: string;
  full_name: string;
  email: string | null;
  mobile: string | null;
  avatar_url: string | null;
  status: string;
  is_platform_admin: boolean;
  email_verified_at: string | null;
  mobile_verified_at: string | null;
  last_login_at: string | null;
  created_at: string;
  /** Two-step sign-in (authenticator app) turned on. */
  mfa_enabled_at?: string | null;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  logo_url: string | null;
  status: string;
  timezone: string;
  currency: string;
}

export interface MembershipSummary {
  id: string;
  organization: OrganizationSummary;
  role_code: string;
  role_name: string;
  branch_id: string | null;
  status: string;
  permissions: string[];
}

export interface MeResponse {
  user: User;
  memberships: MembershipSummary[];
  is_platform_admin: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_new_user: boolean;
  user: User;
}

export interface OTPRequestResponse {
  identifier: string;
  channel: string;
  expires_in: number;
  resend_in: number;
  debug_code?: string | null;
}

export interface SessionInfo {
  id: string;
  device_label: string | null;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_seen_at: string | null;
  expires_at: string;
  is_current: boolean;
}

export interface Organization {
  id: string;
  slug: string;
  code: string;
  name: string;
  legal_name: string | null;
  business_type: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  logo_url: string | null;
  description: string | null;
  address: Record<string, unknown> | null;
  timezone: string;
  currency: string;
  locale: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export type SettingsMap = Record<string, Record<string, unknown>>;

export interface Domain {
  id: number;
  domain: string;
  is_primary: boolean;
  is_verified: boolean;
  verification_token: string | null;
  verified_at: string | null;
  created_at: string;
}

export interface Member {
  id: string;
  user: User;
  role_code: string;
  role_name: string;
  branch_id: string | null;
  status: string;
  invited_at: string | null;
  accepted_at: string | null;
  created_at: string;
}

export interface Role {
  id: number;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  scope: string;
  is_custom: boolean;
  permissions: string[];
}

export interface Permission {
  code: string;
  module: string;
  description: string | null;
}

export interface AuditLog {
  id: string;
  actor_type: string;
  actor_label: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip_address: string | null;
  request_id: string | null;
  purpose: string | null;
  created_at: string;
}

export interface PlatformStats {
  organizations_total: number;
  organizations_active: number;
  users_total: number;
  audit_events_24h: number;
}

export type AuditPage = Page<AuditLog>;
