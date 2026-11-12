"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { titleCase } from "@/lib/format";
import type { Permission, Role } from "@/types/auth";

export default function RolesPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const roles = useQuery({ queryKey: ["roles", orgId], queryFn: () => organizationsService.roles(orgId!), enabled: !!orgId });
  const permissions = useQuery({ queryKey: ["permissions", orgId], queryFn: () => organizationsService.permissions(orgId!), enabled: !!orgId });
  const [selected, setSelected] = useState<number | null>(null);
  const canWrite = hasPermission("roles:write");
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["roles", orgId] });

  const grouped = useMemo(() => {
    const map = new Map<string, Permission[]>();
    for (const p of permissions.data ?? []) map.set(p.module, [...(map.get(p.module) ?? []), p]);
    return [...map.entries()];
  }, [permissions.data]);

  const active = (roles.data ?? []).find((r) => r.id === selected) ?? roles.data?.[0];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Roles & permissions"
        description="System roles are fixed. Create custom roles when a team member needs a different mix of permissions."
        actions={canWrite && orgId ? <CreateRoleDialog orgId={orgId} grouped={grouped} systemRoles={(roles.data ?? []).filter((r) => r.is_system)} onDone={invalidate} /> : null}
      />
      {roles.isLoading || permissions.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <div className="space-y-1">
            {(roles.data ?? []).map((r) => (
              <button
                key={r.id}
                onClick={() => setSelected(r.id)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${active?.id === r.id ? "bg-accent text-accent-foreground" : "hover:bg-muted"}`}
              >
                <span>{r.name}</span>
                {r.is_custom ? <Badge variant="outline">custom</Badge> : null}
              </button>
            ))}
          </div>
          {active && orgId ? <RoleDetail key={active.id} orgId={orgId} role={active} grouped={grouped} canWrite={canWrite} onChanged={invalidate} /> : null}
        </div>
      )}
    </div>
  );
}

function RoleDetail({ orgId, role, grouped, canWrite, onChanged }: { orgId: string; role: Role; grouped: [string, Permission[]][]; canWrite: boolean; onChanged: () => void }) {
  const [perms, setPerms] = useState<Set<string>>(new Set(role.permissions));
  const editable = canWrite && role.is_custom;
  const save = useMutation({
    mutationFn: () => organizationsService.updateRole(orgId, role.id, { permissions: [...perms] }),
    onSuccess: () => { toast.success("Role saved"); onChanged(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => organizationsService.deleteRole(orgId, role.id),
    onSuccess: () => { toast.success("Role deleted"); onChanged(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle>{role.name}</CardTitle>
          <CardDescription>
            <code className="text-xs">{role.code}</code> · {perms.size} permissions {role.is_system ? "· system role (read-only)" : ""}
          </CardDescription>
        </div>
        {editable ? (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm("Delete this role?")) remove.mutate(); }}>Delete</Button>
            <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>Save</Button>
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-5 sm:grid-cols-2">
        {grouped.map(([module, list]) => (
          <div key={module} className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titleCase(module)}</p>
            {list.map((p) => (
              <label key={p.code} className="flex items-start gap-2 text-sm">
                <Checkbox
                  checked={perms.has(p.code)}
                  disabled={!editable}
                  onCheckedChange={(v) => {
                    const next = new Set(perms);
                    if (v) next.add(p.code); else next.delete(p.code);
                    setPerms(next);
                  }}
                />
                <span>
                  <span className="font-medium">{p.code.split(":")[1].replace(/_/g, " ")}</span>
                  <span className="block text-xs text-muted-foreground">{p.description}</span>
                </span>
              </label>
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function CreateRoleDialog({ orgId, grouped, systemRoles, onDone }: { orgId: string; grouped: [string, Permission[]][]; systemRoles: Role[]; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [cloneFrom, setCloneFrom] = useState("");
  const [perms, setPerms] = useState<Set<string>>(new Set());
  const create = useMutation({
    mutationFn: () => organizationsService.createRole(orgId, { code, name, permissions: [...perms], clone_from: cloneFrom || undefined }),
    onSuccess: () => { toast.success("Role created"); setOpen(false); setName(""); setCode(""); setPerms(new Set()); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus /> New role</Button></DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create a custom role</DialogTitle>
          <DialogDescription>You can only grant permissions you hold yourself.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="role_name">
              <Input id="role_name" required value={name} onChange={(e) => { setName(e.target.value); if (!code) setCode(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_")); }} />
            </Field>
            <Field label="Code" htmlFor="role_code" hint="lowercase letters, numbers, underscores">
              <Input id="role_code" required pattern="^[a-z][a-z0-9_]*$" value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
          </div>
          <Field label="Start from a system role (optional)" htmlFor="clone_from">
            <select id="clone_from" className="h-10 w-full rounded-lg border px-3 text-sm" value={cloneFrom} onChange={(e) => setCloneFrom(e.target.value)}>
              <option value="">— none —</option>
              {systemRoles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
            </select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            {grouped.map(([module, list]) => (
              <div key={module} className="space-y-1.5">
                <p className="text-xs font-semibold uppercase text-muted-foreground">{titleCase(module)}</p>
                {list.map((p) => (
                  <label key={p.code} className="flex items-center gap-2 text-sm">
                    <Checkbox checked={perms.has(p.code)} onCheckedChange={(v) => { const n = new Set(perms); if (v) n.add(p.code); else n.delete(p.code); setPerms(n); }} />
                    {p.code.split(":")[1].replace(/_/g, " ")}
                  </label>
                ))}
              </div>
            ))}
          </div>
          <DialogFooter><Button type="submit" disabled={create.isPending}>Create role</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
