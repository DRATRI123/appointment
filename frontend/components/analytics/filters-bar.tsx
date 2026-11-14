"use client";

import { useQuery } from "@tanstack/react-query";
import { catalogService } from "@/services/catalog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { toISODate } from "@/lib/format";
import type { AnalyticsFilters } from "@/types/analytics";

export type Preset = "today" | "7d" | "30d" | "90d" | "month" | "last_month" | "custom";
export const PRESET_LABEL: Record<Preset, string> = { today: "Today", "7d": "Last 7 days", "30d": "Last 30 days", "90d": "Last 90 days", month: "This month", last_month: "Last month", custom: "Custom range" };

export function presetRange(p: Preset, now = new Date()): { from: string; to: string } {
  const d = (n: number) => { const x = new Date(now); x.setDate(x.getDate() - n); return toISODate(x); };
  switch (p) {
    case "today": return { from: d(0), to: d(0) };
    case "7d": return { from: d(6), to: d(0) };
    case "90d": return { from: d(89), to: d(0) };
    case "month": return { from: toISODate(new Date(now.getFullYear(), now.getMonth(), 1)), to: d(0) };
    case "last_month": return { from: toISODate(new Date(now.getFullYear(), now.getMonth() - 1, 1)), to: toISODate(new Date(now.getFullYear(), now.getMonth(), 0)) };
    default: return { from: d(29), to: d(0) };
  }
}

/** One row of filters above everything they scope: date range first, then branch and professional. */
export function FiltersBar({ preset, onPreset, filters, onChange, showProfessional = true, showBranch = true }: {
  preset: Preset; onPreset: (p: Preset) => void; filters: AnalyticsFilters; onChange: (f: AnalyticsFilters) => void; showProfessional?: boolean; showBranch?: boolean;
}) {
  const branches = useQuery({ queryKey: ["branches", "filter"], queryFn: () => catalogService.branches(false), enabled: showBranch });
  const pros = useQuery({ queryKey: ["professionals", "filter"], queryFn: () => catalogService.professionals(), enabled: showProfessional });
  return (
    <div className="flex flex-wrap items-end gap-2" data-testid="filters-bar">
      <NativeSelect aria-label="Date range" className="w-40" value={preset} onChange={(e) => { const p = e.target.value as Preset; onPreset(p); if (p !== "custom") onChange({ ...filters, ...presetRange(p) }); }}>
        {(Object.keys(PRESET_LABEL) as Preset[]).map((p) => <option key={p} value={p}>{PRESET_LABEL[p]}</option>)}
      </NativeSelect>
      {preset === "custom" ? (
        <>
          <Input type="date" aria-label="From" className="w-40" value={filters.from ?? ""} max={filters.to} onChange={(e) => onChange({ ...filters, from: e.target.value })} />
          <Input type="date" aria-label="To" className="w-40" value={filters.to ?? ""} min={filters.from} onChange={(e) => onChange({ ...filters, to: e.target.value })} />
        </>
      ) : null}
      {showBranch && (branches.data?.length ?? 0) > 1 ? (
        <NativeSelect aria-label="Branch" className="w-44" value={filters.branch_id ?? ""} onChange={(e) => onChange({ ...filters, branch_id: e.target.value || undefined })}>
          <option value="">All branches</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </NativeSelect>
      ) : null}
      {showProfessional && (pros.data?.length ?? 0) > 1 ? (
        <NativeSelect aria-label="Professional" className="w-48" value={filters.professional_id ?? ""} onChange={(e) => onChange({ ...filters, professional_id: e.target.value || undefined })}>
          <option value="">All professionals</option>{pros.data?.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
        </NativeSelect>
      ) : null}
    </div>
  );
}
