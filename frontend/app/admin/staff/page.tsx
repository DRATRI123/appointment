"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type { Member } from "@/types/auth";

export default function StaffPage() {
  const { currentOrganizationId: orgId, hasPermission, user } = useAuth();
  const queryClient = useQueryClient();
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => organizationsService.members(orgId!), enabled: !!orgId });
  const roles = useQuery({ queryKey: ["roles", orgId], queryFn: () => organizationsService.roles(orgId!), enabled: !!orgId });
  const canWrite = hasPermission("staff:write");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["members", orgId] });
  const updateRole = useMutation({
    mutationFn: ({ id, role_code }: { id: string; role_code: string }) => organizationsService.updateMember(orgId!, id, { role_code }),
    onSuccess: () => { toast.success("Role updated"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const toggleStatus = useMutation({
    mutationFn: (m: Member) => organizationsService.updateMember(orgId!, m.id, { status: m.status === "suspended" ? "active" : "suspended" }),
    onSuccess: () => { toast.success("Status updated"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (m: Member) => organizationsService.removeMember(orgId!, m.id),
    onSuccess: () => { toast.success("Member removed"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const assignableRoles = (roles.data ?? []).filter((r) => r.code !== "customer");

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Staff"
        description="People who can sign in to this organization and what they are allowed to do."
        actions={canWrite && orgId ? <InviteDialog orgId={orgId} roles={assignableRoles.map((r) => [r.code, r.name])} onDone={invalidate} /> : null}
      />
      {members.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Joined</TableHead>
              {canWrite ? <TableHead className="text-right">Actions</TableHead> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {(members.data ?? []).map((m) => {
              const isSelf = m.user.id === user?.id;
              return (
                <TableRow key={m.id} data-testid="member-row">
                  <TableCell className="font-medium">
                    {m.user.full_name} {isSelf ? <span className="text-xs text-muted-foreground">(you)</span> : null}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{m.user.email ?? m.user.mobile}</TableCell>
                  <TableCell>
                    {canWrite && !isSelf ? (
                      <NativeSelect aria-label={`Role of ${m.user.full_name}`} className="h-8 w-44 text-xs" value={m.role_code} onChange={(e) => updateRole.mutate({ id: m.id, role_code: e.target.value })}>
                        {assignableRoles.map((r) => (
                          <option key={r.code} value={r.code}>{r.name}</option>
                        ))}
                      </NativeSelect>
                    ) : (
                      m.role_name
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={m.status === "active" ? "success" : m.status === "invited" ? "warning" : "destructive"}>{m.status}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDateTime(m.accepted_at ?? m.invited_at ?? m.created_at)}</TableCell>
                  {canWrite ? (
                    <TableCell className="text-right">
                      {!isSelf ? (
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="ghost" onClick={() => toggleStatus.mutate(m)}>
                            {m.status === "suspended" ? "Reactivate" : "Suspend"}
                          </Button>
                          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Remove ${m.user.full_name}?`)) remove.mutate(m); }}>
                            Remove
                          </Button>
                        </div>
                      ) : null}
                    </TableCell>
                  ) : null}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function InviteDialog({ orgId, roles, onDone }: { orgId: string; roles: [string, string][]; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ identifier: "", full_name: "", role_code: "receptionist" });
  const invite = useMutation({
    mutationFn: () => organizationsService.invite(orgId, form),
    onSuccess: () => { toast.success("Invitation created. They sign in with that mobile or email."); setOpen(false); setForm({ identifier: "", full_name: "", role_code: "receptionist" }); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><UserPlus /> Add staff</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a staff member</DialogTitle>
          <DialogDescription>They sign in with the mobile number or email you enter here. No password is sent.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }} data-testid="invite-form">
          <Field label="Full name" htmlFor="inv_name">
            <Input id="inv_name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </Field>
          <Field label="Mobile number or email" htmlFor="inv_identifier">
            <Input id="inv_identifier" required value={form.identifier} onChange={(e) => setForm({ ...form, identifier: e.target.value })} />
          </Field>
          <Field label="Role" htmlFor="inv_role">
            <NativeSelect id="inv_role" value={form.role_code} onChange={(e) => setForm({ ...form, role_code: e.target.value })}>
              {roles.map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </NativeSelect>
          </Field>
          <DialogFooter>
            <Button type="submit" disabled={invite.isPending}>Send invitation</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
