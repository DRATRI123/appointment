"use client";

import { useState } from "react";
import { Table2, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface LegendItem { label: string; color: string }

/** Card with title, legend, and a chart/table toggle (the table view is the accessible and exact reading). */
export function ChartFrame({ title, description, legend, table, children, empty }: {
  title: string; description?: string; legend?: LegendItem[];
  table: { columns: string[]; rows: (string | number)[][]; align?: ("left" | "right")[] };
  children: React.ReactNode; empty?: boolean;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card className="gap-3" data-testid="chart-frame">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        <Button size="sm" variant="ghost" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable} className="shrink-0">
          {asTable ? <><BarChart3 /> Chart</> : <><Table2 /> Table</>}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {legend && legend.length > 1 && !asTable ? (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
            {legend.map((l) => <li key={l.label} className="flex items-center gap-1.5"><span className="h-0.5 w-3 rounded-full" style={{ background: l.color, height: 3 }} />{l.label}</li>)}
          </ul>
        ) : null}
        {empty ? <p className="py-10 text-center text-sm text-muted-foreground">No data for this period.</p> : asTable ? (
          <div className="max-h-80 overflow-auto">
            <Table className="text-xs">
              <TableHeader><TableRow>{table.columns.map((c, i) => <TableHead key={c} className={table.align?.[i] === "right" ? "text-right" : ""}>{c}</TableHead>)}</TableRow></TableHeader>
              <TableBody>{table.rows.map((r, i) => <TableRow key={i}>{r.map((v, j) => <TableCell key={j} className={table.align?.[j] === "right" ? "text-right tabular-nums" : ""}>{v}</TableCell>)}</TableRow>)}</TableBody>
            </Table>
          </div>
        ) : children}
      </CardContent>
    </Card>
  );
}

/** Tooltip body: value first (strong), then the label; a short stroke keys the series. Text is React-escaped. */
export function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="min-w-40 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 font-medium text-muted-foreground">{title}</p>
      <ul className="space-y-0.5">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center gap-2">
            {r.color ? <span className="inline-block w-3 rounded-full" style={{ background: r.color, height: 3 }} /> : null}
            <span className="font-semibold tabular-nums">{r.value}</span>
            <span className="text-muted-foreground">{r.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
