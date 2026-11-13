"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ListPlus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { appointmentsService } from "@/services/booking";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

export default function WaitlistPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["waitlist", orgId], queryFn: appointmentsService.waitlist, enabled: !!orgId });
  const remove = useMutation({ mutationFn: (id: string) => appointmentsService.removeWaitlist(id), onSuccess: () => { toast.success("Removed"); queryClient.invalidateQueries({ queryKey: ["waitlist", orgId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Waitlist" description="Customers waiting for a slot. Automatic notifications when a slot frees up arrive with Phase 8." />
      {list.isLoading ? <Skeleton className="h-48" /> : list.data?.length === 0 ? <EmptyState icon={ListPlus} title="Nobody is waiting" body="Add customers to the waitlist from the booking flow when their preferred time is full." /> : (
        <Table>
          <TableHeader><TableRow><TableHead>Customer</TableHead><TableHead>Preferred</TableHead><TableHead>Notes</TableHead><TableHead>Added</TableHead>{hasPermission("appointments:write") ? <TableHead /> : null}</TableRow></TableHeader>
          <TableBody>{list.data?.map((w) => <TableRow key={w.id}><TableCell>{w.customer.full_name}<span className="block text-xs text-muted-foreground">{w.customer.mobile ?? w.customer.email}</span></TableCell><TableCell>{w.preferred_date ? formatDateTime(w.preferred_date) : "Any"}</TableCell><TableCell className="text-muted-foreground">{w.notes ?? "—"}</TableCell><TableCell className="text-muted-foreground">{formatDateTime(w.created_at)}</TableCell>{hasPermission("appointments:write") ? <TableCell className="text-right"><Button size="sm" variant="ghost" onClick={() => remove.mutate(w.id)}>Remove</Button></TableCell> : null}</TableRow>)}</TableBody>
        </Table>
      )}
    </div>
  );
}
