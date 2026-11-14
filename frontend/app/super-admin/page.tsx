"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { ChartFrame, TooltipBox } from "@/components/analytics/chart-frame";
import { StatTile } from "@/components/analytics/stat-tile";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { downloadPrivateFile } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import { compactNumber, compactRupees } from "@/lib/numbers";

const AXIS = { stroke: "var(--viz-axis)", tick: { fill: "var(--viz-muted)", fontSize: 11 }, tickLine: false } as const;
const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/* eslint-disable @typescript-eslint/no-explicit-any */
function DailyBars({ title, description, data, dataKey, label }: { title: string; description: string; data: any[]; dataKey: string; label: string }) {
  return (
    <ChartFrame title={title} description={description} empty={data.every((d) => !d[dataKey])}
      table={{ columns: ["Date", label], align: ["left", "right"], rows: data.map((d) => [shortDate(d.date), d[dataKey]]) }}>
      <div className="h-56 w-full" role="img" aria-label={title}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
            <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={20} />
            <YAxis allowDecimals={false} {...AXIS} axisLine={false} width={40} />
            <Tooltip cursor={{ fill: "var(--viz-grid)", opacity: 0.5 }} content={({ active, payload, label: l }: any) => active && payload?.length ? <TooltipBox title={shortDate(String(l))} rows={[{ label, value: String(payload[0].value), color: "var(--viz-1)" }]} /> : null} />
            <Bar dataKey={dataKey} name={label} fill="var(--viz-1)" maxBarSize={24} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

export default function SuperAdminOverview() {
  const [days, setDays] = useState(30);
  const dash = useQuery({ queryKey: ["platform-dashboard", days], queryFn: () => platformService.dashboard(days), placeholderData: keepPreviousData });
  const exp = useMutation({ mutationFn: (f: "csv" | "xlsx") => downloadPrivateFile(platformService.exportUrl(f), `organizations.${f}`), onError: (e) => toast.error(errorMessage(e)) });
  const t = dash.data?.totals;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Platform overview" description="Tenants, usage and delivery health across the platform."
        actions={<div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => exp.mutate("csv")}><Download /> Organizations CSV</Button><Button size="sm" onClick={() => exp.mutate("xlsx")}><Download /> Excel</Button></div>} />
      <div className="flex"><NativeSelect aria-label="Period" className="w-40" value={days} onChange={(e) => setDays(Number(e.target.value))}>{[7, 30, 90, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}</NativeSelect></div>
      {!t ? <Skeleton className="h-96" /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="platform-tiles">
            <StatTile hero label="Appointments booked" value={compactNumber(t.appointments)} hint={`Across ${t.organizations_active} active organizations`} />
            <StatTile label="Organizations" value={compactNumber(t.organizations)} hint={`${t.organizations_new} new in the period`} />
            <StatTile label="Users" value={compactNumber(t.users)} hint={`${t.users_new} new in the period`} />
            <StatTile label="Verified receipts" value={compactRupees(t.verified_receipts_paise)} hint="Paid to clinics' own UPI accounts" />
            <StatTile label="Messages sent" value={compactNumber(t.notifications_sent)} hint={`${t.notifications_failed} failed`} />
            <StatTile label="Integrations needing attention" value={String(t.integrations_in_error)} hint="Calendars or Zoom that must be reconnected" />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <DailyBars title="Appointments booked per day" description="By booking date, all organizations." data={dash.data!.series} dataKey="appointments" label="appointments" />
            <DailyBars title="New organizations per day" description="Sign-ups by creation date." data={dash.data!.series} dataKey="signups" label="sign-ups" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader><CardTitle className="text-base">Most active organizations</CardTitle></CardHeader><CardContent>
              {dash.data!.top_organizations.length === 0 ? <p className="text-sm text-muted-foreground">No bookings in this period.</p> : (
                <Table className="text-sm"><TableHeader><TableRow><TableHead>Organization</TableHead><TableHead className="text-right">Appointments</TableHead></TableRow></TableHeader>
                  <TableBody>{dash.data!.top_organizations.map((o) => <TableRow key={o.id}><TableCell><Link className="underline-offset-2 hover:underline" href={`/super-admin/organizations/${o.id}`}>{o.name}</Link></TableCell><TableCell className="text-right tabular-nums">{o.appointments}</TableCell></TableRow>)}</TableBody></Table>
              )}
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="text-base">Plans</CardTitle></CardHeader><CardContent>
              <Table className="text-sm"><TableHeader><TableRow><TableHead>Plan</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Organizations</TableHead></TableRow></TableHeader>
                <TableBody>{dash.data!.plans.map((p) => <TableRow key={`${p.plan}-${p.status}`}><TableCell>{p.plan}</TableCell><TableCell className="text-muted-foreground">{p.status === "none" ? "—" : p.status.replace("_", " ")}</TableCell><TableCell className="text-right tabular-nums">{p.organizations}</TableCell></TableRow>)}</TableBody></Table>
              <Link href="/super-admin/subscriptions" className="mt-3 inline-block text-sm underline">Manage plans and subscriptions</Link>
            </CardContent></Card>
          </div>
        </>
      )}
    </div>
  );
}
