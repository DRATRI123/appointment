"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { platformService } from "@/services/platform";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

export default function PlatformUsersPage() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const [search, setSearch] = useState("");
  const users = useQuery({ queryKey: ["platform-users", search], queryFn: () => platformService.users({ search: search || undefined, page_size: 50 }) });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => platformService.setUserStatus(id, status),
    onSuccess: () => { toast.success("User updated"); queryClient.invalidateQueries({ queryKey: ["platform-users"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Users" description="Every account on the platform. Suspending a user signs them out everywhere." actions={<Input placeholder="Search name, email, mobile" className="w-64" value={search} onChange={(e) => setSearch(e.target.value)} />} />
      {users.isLoading ? <Skeleton className="h-64" /> : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last login</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data?.data.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.full_name} {u.is_platform_admin ? <Badge variant="secondary" className="ml-1">platform admin</Badge> : null}</TableCell>
                <TableCell className="text-muted-foreground">{u.email ?? u.mobile}</TableCell>
                <TableCell><Badge variant={u.status === "active" ? "success" : u.status === "suspended" ? "destructive" : "warning"}>{u.status}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(u.last_login_at)}</TableCell>
                <TableCell className="text-right">
                  {u.id !== me?.id ? (
                    u.status === "suspended" ? (
                      <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: u.id, status: "active" })}>Reactivate</Button>
                    ) : (
                      <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setStatus.mutate({ id: u.id, status: "suspended" })}>Suspend</Button>
                    )
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
