"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, Plus, Users } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { customersService } from "@/services/customers";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";

const SEGMENTS: [string, string][] = [["", "All customers"], ["upcoming", "With upcoming appointment"], ["new_30d", "New in last 30 days"], ["returning", "Returning (2+ visits)"], ["inactive_90d", "Inactive 90+ days"]];

export default function CustomersPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("customers:write");
  const [search, setSearch] = useState("");
  const [segment, setSegment] = useState("");
  const [tag, setTag] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();
  const customers = useQuery({
    queryKey: ["customers", orgId, search, segment, tag, page],
    queryFn: () => customersService.list({ search: search || undefined, segment: segment || undefined, tag: tag || undefined, page, page_size: 25 }),
    enabled: !!orgId,
  });
  const pages = customers.data ? Math.max(1, Math.ceil(customers.data.meta.total / customers.data.meta.page_size)) : 1;
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Customers" description="Every patient or client of this organization, with their history, family members, notes and documents." actions={
        <div className="flex gap-2">
          {hasPermission("customers:export") ? <Button asChild variant="outline"><a href={customersService.exportUrl()} download><Download /> Export CSV</a></Button> : null}
          {canWrite ? <Button onClick={() => setCreating(true)}><Plus /> Add customer</Button> : null}
        </div>
      } />
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Input placeholder="Search name, mobile, email or code" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
        <NativeSelect aria-label="Customer segment" value={segment} onChange={(e) => { setPage(1); setSegment(e.target.value); }}>{SEGMENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>
        <Input placeholder="Filter by tag" value={tag} onChange={(e) => { setPage(1); setTag(e.target.value); }} />
      </div>
      {customers.isLoading ? <Skeleton className="h-64" /> : customers.data?.data.length === 0 ? (
        <EmptyState icon={Users} title="No customers match" body="Customers are created automatically when someone books. You can also add them here for phone bookings." />
      ) : (
        <>
          <Table>
            <TableHeader><TableRow><TableHead>Customer</TableHead><TableHead>Contact</TableHead><TableHead>Tags</TableHead><TableHead>Type</TableHead><TableHead>Last visit</TableHead><TableHead>Registered</TableHead></TableRow></TableHeader>
            <TableBody>
              {customers.data?.data.map((c) => (
                <TableRow key={c.id} data-testid="customer-row">
                  <TableCell><Link href={`/admin/customers/${c.id}`} className="font-medium hover:underline">{c.full_name}</Link><span className="block font-mono text-xs text-muted-foreground">{c.customer_code ?? "—"}</span></TableCell>
                  <TableCell className="text-muted-foreground">{c.mobile}<span className="block text-xs">{c.email}</span></TableCell>
                  <TableCell><div className="flex flex-wrap gap-1">{c.tags.map((t) => <Badge key={t} variant="secondary">{t}</Badge>)}</div></TableCell>
                  <TableCell>{c.is_guest ? <Badge variant="outline">guest</Badge> : <Badge variant="success">registered</Badge>}{c.dependents_count ? <span className="ml-1 text-xs text-muted-foreground">+{c.dependents_count} family</span> : null}</TableCell>
                  <TableCell className="text-muted-foreground">{c.last_visit_at ? formatDate(c.last_visit_at) : "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(c.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
            <span>{customers.data?.meta.total} customers</span>
            <div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
          </div>
        </>
      )}
      {creating ? <CustomerDialog onClose={() => setCreating(false)} onSaved={() => { setCreating(false); queryClient.invalidateQueries({ queryKey: ["customers"] }); }} /> : null}
    </div>
  );
}

function CustomerDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ full_name: "", mobile: "", email: "", gender: "", date_of_birth: "", tags: "" });
  const create = useMutation({
    mutationFn: () => customersService.create({ full_name: form.full_name, mobile: form.mobile || undefined, email: form.email || undefined, gender: form.gender || undefined, date_of_birth: form.date_of_birth || undefined, tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean) }),
    onSuccess: () => { toast.success("Customer added"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add customer</DialogTitle><DialogDescription>A mobile number or email is required so bookings can be matched to this record.</DialogDescription></DialogHeader>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} data-testid="customer-form">
          <Field label="Full name" htmlFor="cu_name" className="sm:col-span-2"><Input id="cu_name" required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
          <Field label="Mobile" htmlFor="cu_mobile"><Input id="cu_mobile" inputMode="tel" value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></Field>
          <Field label="Email" htmlFor="cu_email"><Input id="cu_email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Gender" htmlFor="cu_gender"><NativeSelect id="cu_gender" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}><option value="">—</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="undisclosed">Prefer not to say</option></NativeSelect></Field>
          <Field label="Date of birth" htmlFor="cu_dob"><Input id="cu_dob" type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} /></Field>
          <Field label="Tags" htmlFor="cu_tags" className="sm:col-span-2" hint="Comma separated, e.g. vip, diabetic"><Input id="cu_tags" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
          <DialogFooter className="sm:col-span-2"><Button type="submit" disabled={create.isPending}>Add customer</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
