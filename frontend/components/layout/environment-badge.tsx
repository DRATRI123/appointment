"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

const LOOK: Record<string, { label: string; cls: string }> = {
  development: { label: "Development", cls: "bg-amber-100 text-amber-900 border-amber-300" },
  test: { label: "Test", cls: "bg-sky-100 text-sky-900 border-sky-300" },
  staging: { label: "Staging · test data only", cls: "bg-violet-100 text-violet-900 border-violet-300" },
};

/** Which environment this is, so nobody mistakes a test system for the real one. Production shows nothing. */
export function EnvironmentBadge() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api.get<{ environment: string }>("/meta/"), staleTime: Infinity });
  const look = meta.data ? LOOK[meta.data.environment] : undefined;
  if (!look) return null;
  return (
    <span data-testid="environment-badge" title="This is not the live system"
      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${look.cls}`}>
      {look.label}
    </span>
  );
}
