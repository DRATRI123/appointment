export type MeetingProvider = "auto" | "google_meet" | "zoom" | "manual" | "none";

export interface Integration {
  id: string;
  provider: "google_calendar" | "zoom";
  name: string;
  status: "connected" | "disconnected" | "error" | "disabled";
  is_enabled: boolean;
  account: string | null;
  config: { calendar_id?: string; create_meet?: boolean; block_busy?: boolean; show_patient_names?: boolean; default_user?: string };
  professional_id: string | null;
  professional_name: string | null;
  connected_at: string | null;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface MeetingPreference { provider: MeetingProvider; manual_url: string | null; zoom_user: string | null }

export interface ProfessionalConnections {
  professional_id: string;
  professional_name: string;
  is_me: boolean;
  google: Integration | null;
  meeting: MeetingPreference;
  effective_meeting_provider: Exclude<MeetingProvider, "auto">;
  feed_url: string | null;
}

export interface IntegrationsOverview {
  google_configured: boolean;
  google_redirect_uri: string;
  zoom: Integration | null;
  professionals: ProfessionalConnections[];
  can_manage_all: boolean;
}

export interface IntegrationLog { action: string; status: string; error: string | null; duration_ms: number | null; created_at: string }

export interface SyncIssue {
  id: number;
  provider: string;
  appointment_id: string;
  appointment_reference: string;
  appointment_start_at: string;
  professional_name: string | null;
  status: string;
  attempts: number;
  last_error: string | null;
  next_attempt_at: string | null;
}

export const MEETING_PROVIDER_LABEL: Record<MeetingProvider, string> = {
  auto: "Automatic", google_meet: "Google Meet", zoom: "Zoom", manual: "My own meeting link", none: "No video link",
};
