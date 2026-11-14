"use client";

import { useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, FileSpreadsheet, ShieldAlert } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { analyticsService } from "@/services/analytics";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { FiltersBar, presetRange, type Preset } from "@/components/analytics/filters-bar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { downloadPrivateFile } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import { cn, formatPaise } from "@/lib/utils";
import type { AnalyticsFilters, ReportColumn, ReportInfo } from "@/types/analytics";

function cell(value: string | number | null | undefined, col: ReportColumn) {
  if (value === null || value === undefined || value === "") return "—";
  if (col.type === "money") return formatPaise(Number(value));
  if (col.type === "percent") return `${(Number(value) * 100).toFixed(1)}%`;
  if (col.type === "date") return new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  if (col.type === "datetime") return new Date(String(value).replace(" ", "T")).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  return String(value);
}
const numeric = (c: ReportColumn) => ["int", "money", "percent"].includes(c.type);

export default function ReportsPage() {
  const { currentOrganizationId: orgId } = useAuth();
  const reports = useQuery({ queryKey: ["reports-list", orgId], queryFn: analyticsService.reports, enabled: !!orgId });
  const [selected, setSelected] = useState<string | null>(null);
  const [preset, setPreset] = useState<Preset>("30d");
  const [filters, setFilters] = useState<AnalyticsFilters>(() => presetRange("30d"));
  const [page, setPage] = useState(1);
  const active: ReportInfo | undefined = reports.data?.find((r) => r.key === (selected ?? reports.data?.[0]?.key));
  const result = useQuery({
    queryKey: ["report", orgId, active?.key, filters, page],
    queryFn: () => analyticsService.report(active!.key, { ...filters, page, page_size: 50 }),
    enabled: !!active, placeholderData: keepPreviousData,
  });
  const download = useMutation({
    mutationFn: (format: "csv" | "xlsx") => downloadPrivateFile(analyticsService.exportUrl(active!.key, filters, format), `${active!.key}_${filters.from}_${filters.to}.${format}`, orgId),
    onSuccess: () => toast.success("Download started"), onError: (e) => toast.error(errorMessage(e)),
  });
  const r = result.data;
  const pages = r ? Math.max(1, Math.ceil(r.total_rows / r.page_size)) : 1;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Reports" description="Tables behind the dashboard, ready for your accountant or spreadsheet. Downloads are recorded in the audit log." />
      {reports.isLoading ? <Skeleton className="h-64" /> : !reports.data?.length ? <EmptyState icon={FileSpreadsheet} title="No reports available" body="You need report permissions to see this page." /> : (
        <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
          <nav className="space-y-1" aria-label="Reports" data-testid="report-list">
            {reports.data.map((rep) => (
              <button key={rep.key} type="button" onClick={() => { setSelected(rep.key); setPage(1); }} aria-current={active?.key === rep.key}
                className={cn("w-full rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-muted", active?.key === rep.key && "bg-accent font-medium text-accent-foreground")}>
                {rep.title}
              </button>
            ))}
          </nav>
          {active ? (
            <Card className="min-w-0">
              <CardHeader className="space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><CardTitle>{active.title}</CardTitle><CardDescription>{active.description}</CardDescription></div>
                  {active.can_export ? (
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => download.mutate("csv")} disabled={download.isPending} data-testid="export-csv"><Download /> CSV</Button>
                      <Button size="sm" onClick={() => download.mutate("xlsx")} disabled={download.isPending} data-testid="export-xlsx"><FileSpreadsheet /> Excel</Button>
                    </div>
                  ) : null}
                </div>
                <FiltersBar preset={preset} onPreset={(p) => { setPreset(p); setPage(1); }} filters={filters} onChange={(f) => { setFilters(f); setPage(1); }} />
                {active.contains_personal_data ? <Alert><ShieldAlert /><AlertDescription>Contains patients&apos; personal details. Share downloads only with people who need them, and delete copies you no longer need.</AlertDescription></Alert> : null}
              </CardHeader>
              <CardContent className="space-y-3">
                {result.isError ? <p className="text-sm text-destructive">{errorMessage(result.error)}</p> : !r ? <Skeleton className="h-64" /> : r.total_rows === 0 ? (
                  <p className="py-10 text-center text-sm text-muted-foreground">Nothing in this period.</p>
                ) : (
                  <>
                    <Table className="text-xs" data-testid="report-table">
                      <TableHeader><TableRow>{r.columns.map((c) => <TableHead key={c.key} className={cn("whitespace-nowrap", numeric(c) && "text-right")}>{c.label}</TableHead>)}</TableRow></TableHeader>
                      <TableBody>{r.rows.map((row, i) => <TableRow key={i}>{r.columns.map((c) => <TableCell key={c.key} className={cn("max-w-64 truncate", numeric(c) && "text-right tabular-nums")}>{cell(row[c.key], c)}</TableCell>)}</TableRow>)}</TableBody>
                      {Object.keys(r.totals).length ? (
                        <TableFooter><TableRow>{r.columns.map((c, i) => <TableCell key={c.key} className={cn("font-semibold", numeric(c) && "text-right tabular-nums")}>{c.key in r.totals ? cell(r.totals[c.key], c) : i === 0 ? "Total" : ""}</TableCell>)}</TableRow></TableFooter>
                      ) : null}
                    </Table>
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                      <span>{r.total_rows} {r.total_rows === 1 ? "row" : "rows"}{r.truncated ? " (first 50,000)" : ""}</span>
                      {pages > 1 ? <div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div> : null}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  );
}
