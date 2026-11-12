"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

export default function PlatformOrganizationsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const orgs = useQuery({ queryKey: ["platform-orgs", search, page], queryFn: () => platformService.organizations({ search: search || undefined, page, page_size: 25 }) });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => platformService.setOrganizationStatus(id, status, "Changed from platform console"),
    onSuccess: () => { toast.success("Organization updated"); queryClient.invalidateQueries({ queryKey: ["platform-orgs"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Organizations" description="Activate, suspend or close tenants." actions={<Input placeholder="Search name or slug" className="w-64" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />} />
      {orgs.isLoading ? <Skeleton className="h-64" /> : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Organization</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {orgs.data?.data.map((o) => (
              <TableRow key={o.id}>
                <TableCell>
                  <p className="font-medium">{o.name}</p>
                  <p className="text-xs text-muted-foreground">{o.slug} · {o.code}</p>
                </TableCell>
                <TableCell className="text-muted-foreground">{o.business_type ?? "—"}</TableCell>
                <TableCell><Badge variant={o.status === "active" ? "success" : o.status === "suspended" ? "destructive" : "warning"}>{o.status}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(o.created_at)}</TableCell>
                <TableCell className="text-right">
                  {o.status === "active" ? (
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setStatus.mutate({ id: o.id, status: "suspended" })}>Suspend</Button>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: o.id, status: "active" })}>Activate</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {orgs.data ? <p className="mt-3 text-sm text-muted-foreground">{orgs.data.meta.total} organizations</p> : null}
    </div>
  );
}
