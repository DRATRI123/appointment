"use client";

import { useQuery } from "@tanstack/react-query";
import { systemService } from "@/services/system";

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system", "readiness"],
    queryFn: systemService.readiness,
    refetchInterval: 30_000,
  });
}
