import { api } from "@/lib/api-client";
import type { AppMeta, HealthStatus } from "@/types/api";

export const systemService = {
  health: () => api.get<HealthStatus>("/health"),
  readiness: () => api.get<HealthStatus>("/health/ready"),
  meta: () => api.get<AppMeta>("/meta/"),
};
