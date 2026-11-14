"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, BarChart3, Briefcase, Building2, CalendarClock, CalendarDays, ClipboardList, CreditCard, FileSpreadsheet, Settings, Stethoscope, UsersRound } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { analyticsService } from "@/services/analytics";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { FiltersBar, presetRange, PRESET_LABEL, type Preset } from "@/components/analytics/filters-bar";
import { StatTile } from "@/components/analytics/stat-tile";
import { BookingHeatmap, BreakdownBars, OutcomesChart, ReceiptsChart, UtilizationBars } from "@/components/analytics/charts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { compactNumber, compactRupees, percent } from "@/lib/numbers";
import type { AnalyticsFilters } from "@/types/analytics";

const ATTENTION: Record<string, [string, string]> = {
  payments_to_verify: ["payments waiting for verification", "/admin/payments/verification"],
  refunds_to_approve: ["refunds to approve or send", "/admin/refunds"],
  unmatched_bank_credits: ["bank credits to reconcile", "/admin/reconciliation"],
  failed_notifications: ["messages that failed to send", "/admin/notifications"],
  calendar_sync_problems: ["calendar or meeting sync problems", "/admin/integrations"],
};

const SETUP = [
  { href: "/admin/branches", icon: Building2, title: "Add branches", body: "Locations with their own hours, contact details and UPI accounts." },
  { href: "/admin/services", icon: Briefcase, title: "Create services", body: "Consultations and treatments with prices, durations and advance rules." },
  { href: "/admin/professionals", icon: Stethoscope, title: "Add professionals", body: "Doctors and therapists with fees, schedules and services." },
  { href: "/admin/staff", icon: UsersRound, title: "Invite your team", body: "Receptionists, doctors and accountants sign in with their mobile number." },
  { href: "/admin/settings", icon: Settings, title: "Booking & payment rules", body: "Advance payment, cancellation windows, reminders and branding." },
];
const QUICK = [
  { href: "/admin/calendar", icon: CalendarDays, title: "Calendar" },
  { href: "/admin/appointments", icon: ClipboardList, title: "Appointments" },
  { href: "/admin/payments", icon: CreditCard, title: "Payments" },
];

function QuickLinks() {
  return (
    <div className="grid gap-3 sm:grid-cols-3" data-testid="quick-links">
      {QUICK.map((q) => (
        <Link key={q.href} href={q.href} className="rounded-xl border p-4 transition-colors hover:border-primary/40 hover:bg-muted/30">
          <q.icon className="mb-2 size-5 text-primary" /><p className="font-medium">{q.title}</p>
        </Link>
      ))}
    </div>
  );
}

function SetupChecklist() {
  return (
    <div className="space-y-3" data-testid="setup-checklist">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Set up next</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SETUP.map((n) => (
          <Link key={n.href} href={n.href} className="rounded-xl border p-4 transition-colors hover:border-primary/40 hover:bg-muted/30">
            <span className="mb-2 grid size-9 place-items-center rounded-lg bg-accent text-accent-foreground"><n.icon className="size-4" /></span>
            <p className="font-medium">{n.title}</p><p className="text-sm text-muted-foreground">{n.body}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function AdminOverview() {
  const { hasPermission, currentMembership } = useAuth();
  if (!hasPermission("reports:read")) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <PageHeader title={currentMembership?.organization.name ?? "Overview"} description={`You are signed in as ${currentMembership?.role_name ?? "staff"}.`} />
        <QuickLinks />
      </div>
    );
  }
  return <AdminDashboard />;
}

function AdminDashboard() {
  const { currentMembership, currentOrganizationId: orgId, hasPermission } = useAuth();
  const [preset, setPreset] = useState<Preset>("30d");
  const [filters, setFilters] = useState<AnalyticsFilters>(() => presetRange("30d"));
  const dash = useQuery({ queryKey: ["dashboard", orgId, filters], queryFn: () => analyticsService.dashboard(filters), enabled: !!orgId, placeholderData: keepPreviousData, retry: false });
  const org = currentMembership?.organization;
  const d = dash.data;
  const k = d?.kpis;
  const v = (key: string) => k?.[key]?.value ?? 0;
  const p = (key: string) => k?.[key]?.previous ?? null;
  const cmp = preset === "custom" ? "previous period" : `previous ${PRESET_LABEL[preset].replace(/^Last /, "").replace(/^This /, "").toLowerCase()}`;
  const attention = d ? Object.entries(d.attention).filter(([, n]) => n > 0) : [];
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title={org?.name ?? "Dashboard"} description="How the clinic is doing. Figures use the clinic's time zone."
        actions={<div className="flex gap-2">{hasPermission("reports:read") ? <Button asChild variant="outline"><Link href="/admin/reports"><FileSpreadsheet /> Reports</Link></Button> : null}
          {org ? <Button asChild variant="ghost"><Link href={`/${org.slug}`} target="_blank">Public page <ArrowRight /></Link></Button> : null}</div>} />
      <FiltersBar preset={preset} onPreset={setPreset} filters={filters} onChange={setFilters} />
      {dash.isError ? <EmptyState icon={BarChart3} title="Dashboard unavailable" body={errorMessage(dash.error)} /> : !d ? <Skeleton className="h-96" /> : (
        <div className="space-y-6" data-testid="dashboard">
          {v("appointments") === 0 && (p("appointments") ?? 0) === 0 ? <SetupChecklist /> : null}
          {attention.length ? (
            <Card className="border-warning/50 bg-warning/5 py-4" data-testid="attention">
              <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <span className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4 text-warning" /> Needs attention</span>
                {attention.map(([key, n]) => <Link key={key} href={ATTENTION[key]?.[1] ?? "/admin"} className="underline-offset-2 hover:underline"><strong>{n}</strong> {ATTENTION[key]?.[0] ?? key}</Link>)}
              </CardContent>
            </Card>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile hero label="Money received" value={compactRupees(v("revenue_paise"))} current={v("revenue_paise")} previous={p("revenue_paise")} format={compactRupees} comparison={cmp}
              hint={`${compactRupees(v("gross_receipts_paise"))} verified − ${compactRupees(v("refunds_paise"))} refunded`} />
            <StatTile label="Appointments" value={compactNumber(v("appointments"))} current={v("appointments")} previous={p("appointments")} comparison={cmp} hint={`${v("booked")} booked`} />
            <StatTile label="Customers seen" value={compactNumber(v("customers"))} current={v("customers")} previous={p("customers")} comparison={cmp} hint={`${v("new_customers")} new, ${v("returning_customers")} returning`} />
            <StatTile label="Cancellation rate" value={percent(v("cancellation_rate"))} current={v("cancellation_rate")} previous={p("cancellation_rate")} upIsGood={false} format={(n) => percent(n)} comparison={cmp} />
            <StatTile label="No-show rate" value={percent(v("no_show_rate"))} current={v("no_show_rate")} previous={p("no_show_rate")} upIsGood={false} format={(n) => percent(n)} comparison={cmp} hint="Of appointments that were due" />
            <StatTile label="Booked value" value={compactRupees(v("booked_value_paise"))} current={v("booked_value_paise")} previous={p("booked_value_paise")} format={compactRupees} comparison={cmp} hint={`Average ${compactRupees(v("average_value_paise"))} per booking`} />
            <Card className="gap-1 py-4" data-testid="today">
              <CardHeader><p className="flex items-center gap-1.5 text-sm text-muted-foreground"><CalendarClock className="size-4" /> Today</p></CardHeader>
              <CardContent className="space-y-0.5 text-sm">
                <p className="text-2xl font-semibold">{d.today.total}</p>
                <p className="text-xs text-muted-foreground">{d.today.upcoming} upcoming · {d.today.checked_in} in clinic · {d.today.completed} done{d.today.no_show ? ` · ${d.today.no_show} no-show` : ""}{d.today.awaiting_payment ? ` · ${d.today.awaiting_payment} awaiting payment` : ""}</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <OutcomesChart series={d.series} />
            <ReceiptsChart series={d.series} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            <BreakdownBars title="Top services" description="By appointments in the period." rows={d.by_service} metric="appointments" />
            <BreakdownBars title="Receipts by professional" description="Verified payments for their appointments." rows={d.by_professional} metric="revenue_paise" />
            <UtilizationBars rows={d.by_professional} />
            <BookingHeatmap cells={d.heatmap} />
            <BreakdownBars title="Booking channels" description="Where appointments came from." rows={d.by_source} metric="appointments" />
            <BreakdownBars title="Payment methods" description="Verified receipts by method." rows={d.payment_methods} metric="revenue_paise" />
          </div>
          {d.by_branch.length > 1 ? <BreakdownBars title="Branches" description="By appointments in the period." rows={d.by_branch} metric="appointments" /> : null}
          <Card><CardHeader><CardTitle className="text-base">How these numbers are counted</CardTitle><CardDescription>
            Appointments are counted on their appointment date. Money received is what staff verified against the bank in the period, minus refunds sent; UTRs that are still waiting for verification are not counted. Rates compare with the {cmp}.
          </CardDescription></CardHeader></Card>
        </div>
      )}
    </div>
  );
}
