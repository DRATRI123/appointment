"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartFrame, TooltipBox } from "@/components/analytics/chart-frame";
import { compactNumber, compactRupees, percent } from "@/lib/numbers";
import { formatPaise } from "@/lib/utils";
import type { Breakdown, DayPoint, HeatCell } from "@/types/analytics";

const AXIS = { stroke: "var(--viz-axis)", tick: { fill: "var(--viz-muted)", fontSize: 11 }, tickLine: false } as const;
const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const longDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });

/* eslint-disable @typescript-eslint/no-explicit-any */
type TipProps = { active?: boolean; payload?: readonly any[]; label?: any };

export function OutcomesChart({ series }: { series: DayPoint[] }) {
  const legend = [{ label: "Booked", color: "var(--viz-1)" }, { label: "Cancelled", color: "var(--viz-2)" }, { label: "No-show", color: "var(--viz-3)" }];
  const empty = series.every((p) => !p.booked && !p.cancelled && !p.no_show);
  return (
    <ChartFrame title="Appointments by day" description="By appointment date. Booked includes upcoming, in progress and completed." legend={legend} empty={empty}
      table={{ columns: ["Date", "Booked", "Cancelled", "No-show"], align: ["left", "right", "right", "right"], rows: series.map((p) => [longDate(p.date), p.booked, p.cancelled, p.no_show]) }}>
      <div className="h-64 w-full" role="img" aria-label="Appointments by day: booked, cancelled and no-show">
        <ResponsiveContainer>
          <BarChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -12 }} barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
            <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={16} />
            <YAxis allowDecimals={false} {...AXIS} axisLine={false} width={40} />
            <Tooltip cursor={{ fill: "var(--viz-grid)", opacity: 0.5 }} content={({ active, payload, label }: TipProps) => active && payload?.length ? (
              <TooltipBox title={longDate(String(label))} rows={[...payload].reverse().map((p: any) => ({ label: p.name, value: String(p.value), color: p.color }))} />
            ) : null} />
            <Bar dataKey="booked" name="Booked" stackId="a" fill="var(--viz-1)" stroke="var(--card)" strokeWidth={2} maxBarSize={24} />
            <Bar dataKey="cancelled" name="Cancelled" stackId="a" fill="var(--viz-2)" stroke="var(--card)" strokeWidth={2} maxBarSize={24} />
            <Bar dataKey="no_show" name="No-show" stackId="a" fill="var(--viz-3)" stroke="var(--card)" strokeWidth={2} maxBarSize={24} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

export function ReceiptsChart({ series }: { series: DayPoint[] }) {
  const data = series.map((p) => ({ date: p.date, net: Math.max(0, p.revenue_paise - p.refunds_paise), gross: p.revenue_paise, refunds: p.refunds_paise }));
  const empty = data.every((d) => !d.gross && !d.refunds);
  return (
    <ChartFrame title="Money received by day" description="Payments verified by staff that day, minus refunds sent. Unverified UTRs are not counted." empty={empty}
      table={{ columns: ["Date", "Verified", "Refunds", "Net"], align: ["left", "right", "right", "right"], rows: data.map((d) => [longDate(d.date), formatPaise(d.gross), formatPaise(d.refunds), formatPaise(d.gross - d.refunds)]) }}>
      <div className="h-64 w-full" role="img" aria-label="Net money received by day">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
            <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={16} />
            <YAxis tickFormatter={(v) => compactRupees(Number(v))} {...AXIS} axisLine={false} width={56} />
            <Tooltip cursor={{ fill: "var(--viz-grid)", opacity: 0.5 }} content={({ active, payload, label }: TipProps) => active && payload?.length ? (
              <TooltipBox title={longDate(String(label))} rows={[{ label: "net received", value: formatPaise(payload[0].payload.gross - payload[0].payload.refunds), color: "var(--viz-1)" },
                { label: "verified", value: formatPaise(payload[0].payload.gross) }, { label: "refunds sent", value: formatPaise(payload[0].payload.refunds) }]} />
            ) : null} />
            <Bar dataKey="net" name="Net received" fill="var(--viz-1)" maxBarSize={24} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/** Horizontal bars, one series (blue), ranked; value printed at the bar tip. */
export function BreakdownBars({ title, description, rows, metric }: { title: string; description?: string; rows: Breakdown[]; metric: "appointments" | "revenue_paise" }) {
  const top = rows.slice(0, 8);
  const fmt = (v: number) => (metric === "revenue_paise" ? compactRupees(v) : compactNumber(v));
  const max = Math.max(1, ...top.map((r) => r[metric]));
  return (
    <ChartFrame title={title} description={description} empty={top.length === 0}
      table={{ columns: ["Name", "Appointments", "Completed", "Cancelled", "No-show", "Verified receipts"], align: ["left", "right", "right", "right", "right", "right"],
        rows: rows.map((r) => [r.label, r.appointments, r.completed, r.cancelled, r.no_show, formatPaise(r.revenue_paise)]) }}>
      <ul className="space-y-2.5" data-testid="breakdown-bars">
        {top.map((r) => (
          <li key={r.key} className="group grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm" title={`${r.label}: ${fmt(r[metric])}`}>
            <span className="truncate text-muted-foreground">{r.label}</span>
            <span className="relative h-3 rounded-r-[4px]" aria-hidden>
              <span className="absolute inset-y-0 left-0 rounded-r-[4px] bg-[var(--viz-1)] transition-opacity group-hover:opacity-80" style={{ width: `${Math.max(2, (r[metric] / max) * 100)}%` }} />
            </span>
            <span className="tabular-nums font-medium">{fmt(r[metric])}</span>
          </li>
        ))}
        {rows.length > 8 ? <li className="text-xs text-muted-foreground">+{rows.length - 8} more in the table view</li> : null}
      </ul>
    </ChartFrame>
  );
}

/** Professional utilization: booked hours / scheduled hours, a meter per professional. */
export function UtilizationBars({ rows }: { rows: Breakdown[] }) {
  const withData = rows.filter((r) => r.available_minutes);
  return (
    <ChartFrame title="Professional utilization" description="Booked time as a share of scheduled working time." empty={withData.length === 0}
      table={{ columns: ["Professional", "Booked hours", "Scheduled hours", "Utilization", "No-shows"], align: ["left", "right", "right", "right", "right"],
        rows: rows.map((r) => [r.label, (r.booked_minutes / 60).toFixed(1), r.available_minutes ? (r.available_minutes / 60).toFixed(1) : "—", percent(r.utilization), r.no_show]) }}>
      <ul className="space-y-3">
        {withData.slice(0, 8).map((r) => (
          <li key={r.key} className="space-y-1 text-sm" title={`${r.label}: ${percent(r.utilization)}`}>
            <div className="flex justify-between gap-3"><span className="truncate">{r.label}</span><span className="tabular-nums font-medium">{percent(r.utilization)}</span></div>
            <div className="h-2 rounded-full bg-[var(--viz-seq-1)]" aria-hidden><div className="h-2 rounded-full bg-[var(--viz-seq-4)]" style={{ width: `${Math.min(100, (r.utilization ?? 0) * 100)}%` }} /></div>
            <p className="text-xs text-muted-foreground">{(r.booked_minutes / 60).toFixed(1)} of {((r.available_minutes ?? 0) / 60).toFixed(1)} hours</p>
          </li>
        ))}
      </ul>
    </ChartFrame>
  );
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Weekday × hour booking density, one-hue sequential ramp; empty cells recede to the surface. */
export function BookingHeatmap({ cells }: { cells: HeatCell[] }) {
  const hours = cells.length ? Array.from({ length: Math.max(...cells.map((c) => c.hour)) - Math.min(...cells.map((c) => c.hour)) + 1 }, (_, i) => Math.min(...cells.map((c) => c.hour)) + i) : [];
  const max = Math.max(1, ...cells.map((c) => c.appointments));
  const at = (d: number, h: number) => cells.find((c) => c.weekday === d && c.hour === h)?.appointments ?? 0;
  const step = (n: number) => (n === 0 ? 0 : Math.min(5, 1 + Math.floor((n / max) * 4.999)));
  return (
    <ChartFrame title="Busiest times" description="Appointments by weekday and starting hour (clinic time)." empty={cells.length === 0}
      table={{ columns: ["Day", "Hour", "Appointments"], align: ["left", "left", "right"], rows: cells.map((c) => [DAYS[c.weekday], `${String(c.hour).padStart(2, "0")}:00`, c.appointments]) }}>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-[11px]" aria-label="Appointments by weekday and hour">
          <thead><tr><th className="sr-only">Day</th>{hours.map((h) => <th key={h} className="w-8 font-normal text-muted-foreground">{h}</th>)}</tr></thead>
          <tbody>
            {DAYS.map((d, di) => (
              <tr key={d}>
                <th scope="row" className="pr-2 text-left font-normal text-muted-foreground">{d}</th>
                {hours.map((h) => {
                  const n = at(di, h);
                  return <td key={h} className="size-7 rounded-[3px]" style={{ background: `var(--viz-seq-${step(n)})` }} title={`${n} appointment${n === 1 ? "" : "s"} · ${d} ${String(h).padStart(2, "0")}:00`}><span className="sr-only">{n}</span></td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground" aria-hidden>Fewer {[1, 2, 3, 4, 5].map((s) => <span key={s} className="size-3 rounded-[2px]" style={{ background: `var(--viz-seq-${s})` }} />)} More</div>
      </div>
    </ChartFrame>
  );
}
