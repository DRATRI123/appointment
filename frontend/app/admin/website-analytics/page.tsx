"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3, Info } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { api } from "@/lib/api-client";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { errorMessage } from "@/lib/errors";

interface Report {
  totals: { page_views: number; book_clicks: number; booking_views: number; holds: number; bookings: number; website_bookings: number; conversion_percent: number | null };
  daily: { date: string; page_views: number; book_clicks: number; booking_views: number; bookings: number }[];
  top_pages: { key: string; views: number }[];
  traffic_sources: { source: string; views: number }[];
  booking_sources: { source: string; bookings: number }[];
  campaigns: { campaign: string; bookings: number }[];
}

const day = (offset: number) => new Date(Date.now() - offset * 86_400_000).toISOString().slice(0, 10);

export default function WebsiteAnalyticsPage() {
  const { currentOrganizationId: orgId } = useAuth();
  const [from, setFrom] = useState(day(29));
  const [to, setTo] = useState(day(0));
  const report = useQuery({ queryKey: ["website-analytics", orgId, from, to], queryFn: () => api.get<Report>("/website/analytics", { searchParams: { from_date: from, to_date: to } }), enabled: !!orgId });
  const r = report.data;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Website analytics" description="Visits to your clinic website and how many become bookings." />
      <Alert variant="info"><Info /><AlertDescription>Counts are anonymous daily totals: no cookies, no IP addresses, no personal data. Visitors who ask browsers not to be tracked are not counted, so real traffic may be a little higher. “Bookings via website” counts online bookings made on this website or its embedded frame; all online bookings appear in the chart and source lists.</AlertDescription></Alert>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1"><Label htmlFor="wa_from">From</Label><Input id="wa_from" type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></div>
        <div className="space-y-1"><Label htmlFor="wa_to">To</Label><Input id="wa_to" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} /></div>
      </div>
      {report.isLoading ? <Skeleton className="h-96" /> : report.error ? <EmptyState icon={BarChart3} title="No access" body={errorMessage(report.error)} /> : r ? (
        <>
          <dl className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6" data-testid="website-kpis">
            {[
              ["Page views", r.totals.page_views], ["Book clicks", r.totals.book_clicks], ["Booking page views", r.totals.booking_views],
              ["Times reserved", r.totals.holds], ["Bookings via website", r.totals.website_bookings], ["Bookings per 100 views", r.totals.conversion_percent ?? "—"],
            ].map(([label, value]) => (
              <Card key={label as string}><CardContent className="p-4"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd></CardContent></Card>
            ))}
          </dl>
          <Card>
            <CardHeader><CardTitle>Visits and bookings per day</CardTitle></CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={r.daily} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={12} />
                  <YAxis allowDecimals={false} fontSize={12} />
                  <Tooltip />
                  <Area type="monotone" dataKey="page_views" name="Page views" stroke="var(--chart-1, #0f766e)" fill="var(--chart-1, #0f766e)" fillOpacity={0.15} />
                  <Area type="monotone" dataKey="bookings" name="Online bookings" stroke="var(--chart-2, #b45309)" fill="var(--chart-2, #b45309)" fillOpacity={0.2} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <ListCard title="Most viewed pages" rows={r.top_pages.map((p) => [p.key === "home" ? "Home page" : p.key, p.views])} unit="views" />
            <ListCard title="Where visitors came from" description="From the utm_source in your links; “direct” when there was none." rows={r.traffic_sources.map((s) => [s.source, s.views])} unit="views" />
            <ListCard title="Bookings by source" description="Shopify, Instagram, WhatsApp… whatever your links named. “embed” = booked inside your website frame." rows={r.booking_sources.map((s) => [s.source, s.bookings])} unit="bookings" />
            <ListCard title="Bookings by campaign" rows={r.campaigns.map((c) => [c.campaign, c.bookings])} unit="bookings" empty="Add utm_campaign to a link (Booking page & Shopify → link builder) to see campaigns here." />
          </div>
        </>
      ) : null}
    </div>
  );
}

function ListCard({ title, description, rows, unit, empty }: { title: string; description?: string; rows: [string, number][]; unit: string; empty?: string }) {
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle>{description ? <CardDescription>{description}</CardDescription> : null}</CardHeader>
      <CardContent>
        {rows.length ? (
          <ul className="space-y-2">
            {rows.map(([label, value]) => (
              <li key={label} className="space-y-1 text-sm">
                <div className="flex justify-between gap-2"><span className="truncate font-medium">{label}</span><span className="tabular-nums text-muted-foreground">{value} {unit}</span></div>
                <div className="h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${(value / max) * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">{empty ?? "No data in this period yet."}</p>}
      </CardContent>
    </Card>
  );
}
