import { LIMIT_LABEL, type OrgSummary } from "@/types/platform";

/** Usage against plan limits; the fill turns critical when the limit is exceeded (also stated in words). */
export function UsageMeters({ org }: { org: OrgSummary }) {
  const limits = org.subscription?.limits ?? {};
  const rows: [keyof typeof LIMIT_LABEL, number][] = [["branches", org.usage.branches], ["professionals", org.usage.professionals], ["staff", org.usage.staff], ["appointments_per_month", org.usage.appointments_this_month]];
  return (
    <ul className="space-y-3" data-testid="usage-meters">
      {rows.map(([key, used]) => {
        const limit = limits[key];
        const over = limit !== null && limit !== undefined && used > limit;
        return (
          <li key={key} className="space-y-1 text-sm">
            <div className="flex justify-between gap-3"><span>{LIMIT_LABEL[key]}</span><span className="tabular-nums">{used}{limit !== null && limit !== undefined ? ` of ${limit}` : " · no limit"}{over ? <span className="ml-1 font-medium text-[var(--viz-down-bad)]">over limit</span> : null}</span></div>
            {limit ? <div className="h-2 rounded-full bg-[var(--viz-seq-1)]" aria-hidden><div className="h-2 rounded-full" style={{ width: `${Math.min(100, (used / limit) * 100)}%`, background: over ? "var(--viz-down-bad)" : "var(--viz-seq-4)" }} /></div> : null}
          </li>
        );
      })}
    </ul>
  );
}
