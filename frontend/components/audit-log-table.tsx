"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import type { Page } from "@/types/api";
import type { AuditLog } from "@/types/auth";

export function AuditLogTable({ page, isLoading, onPage }: { page: Page<AuditLog> | undefined; isLoading: boolean; onPage: (p: number) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  if (isLoading || !page) return <Skeleton className="h-64 w-full" />;
  const pages = Math.max(1, Math.ceil(page.meta.total / page.meta.page_size));
  return (
    <div className="space-y-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>When</TableHead>
            <TableHead>Actor</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Entity</TableHead>
            <TableHead>IP</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.data.map((row) => (
            <>
              <TableRow key={row.id}>
                <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(row.created_at)}</TableCell>
                <TableCell>{row.actor_label ?? row.actor_type}</TableCell>
                <TableCell><Badge variant="outline" className="font-mono text-[11px]">{row.action}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{row.entity_type}{row.entity_id ? ` · ${row.entity_id.slice(0, 12)}` : ""}</TableCell>
                <TableCell className="text-muted-foreground">{row.ip_address ?? "—"}</TableCell>
                <TableCell className="text-right">
                  {row.before || row.after || row.purpose ? (
                    <Button size="sm" variant="ghost" onClick={() => setOpen(open === row.id ? null : row.id)}>{open === row.id ? "Hide" : "Details"}</Button>
                  ) : null}
                </TableCell>
              </TableRow>
              {open === row.id ? (
                <TableRow key={`${row.id}-details`} className="bg-muted/30 hover:bg-muted/30">
                  <TableCell colSpan={6}>
                    {row.purpose ? <p className="mb-2 text-sm">Purpose: {row.purpose}</p> : null}
                    <div className="grid gap-3 sm:grid-cols-2">
                      <pre className="overflow-x-auto rounded-md bg-background p-3 text-xs">before: {JSON.stringify(row.before, null, 2)}</pre>
                      <pre className="overflow-x-auto rounded-md bg-background p-3 text-xs">after: {JSON.stringify(row.after, null, 2)}</pre>
                    </div>
                  </TableCell>
                </TableRow>
              ) : null}
            </>
          ))}
        </TableBody>
      </Table>
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{page.meta.total} events</span>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={page.meta.page <= 1} onClick={() => onPage(page.meta.page - 1)}>Previous</Button>
          <span>Page {page.meta.page} of {pages}</span>
          <Button size="sm" variant="outline" disabled={page.meta.page >= pages} onClick={() => onPage(page.meta.page + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
