"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, QrCode } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { upiAccountsService } from "@/services/payments";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { NativeSelect } from "@/components/ui/native-select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { ImageUpload } from "@/components/forms/image-upload";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { errorMessage } from "@/lib/errors";
import type { UPIAccount } from "@/types/payment";

export default function UPIAccountsPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("upi_accounts:write");
  const queryClient = useQueryClient();
  const accounts = useQuery({ queryKey: ["upi-accounts", orgId], queryFn: upiAccountsService.list, enabled: !!orgId });
  const services = useQuery({ queryKey: ["services-all"], queryFn: () => catalogService.services(), enabled: !!orgId && canWrite });
  const [editing, setEditing] = useState<UPIAccount | "new" | null>(null);
  const [preview, setPreview] = useState<UPIAccount | null>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["upi-accounts", orgId] });
  const remove = useMutation({ mutationFn: (id: string) => upiAccountsService.remove(id), onSuccess: () => { toast.success("Account removed"); invalidate(); }, onError: (e) => toast.error(errorMessage(e)) });
  const assign = useMutation({ mutationFn: ({ service_id, account }: { service_id: string; account: string | null }) => upiAccountsService.assign(service_id, account), onSuccess: (r) => { toast.success(r.detail); invalidate(); queryClient.invalidateQueries({ queryKey: ["services-all"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const active = (accounts.data ?? []).filter((a) => a.is_active);
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader title="UPI accounts" description="Customers pay these accounts directly from any UPI app. No payment gateway sits in between and no fee is taken." actions={canWrite ? <Button onClick={() => setEditing("new")}><Plus /> Add UPI account</Button> : null} />
      <Alert variant="info"><AlertDescription>Which account collects a booking: the service&apos;s own account if set, otherwise the branch default, otherwise the organization default.</AlertDescription></Alert>
      {accounts.isLoading ? <Skeleton className="h-40" /> : accounts.data?.length === 0 ? (
        <EmptyState icon={QrCode} title="No UPI account yet" body="Add your clinic's UPI ID so customers can pay the advance when they book." action={canWrite ? <Button onClick={() => setEditing("new")}>Add UPI account</Button> : undefined} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {accounts.data?.map((a) => (
            <Card key={a.id} data-testid="upi-account" className="gap-3 py-5">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <div><CardTitle>{a.display_name}</CardTitle><CardDescription className="font-mono">{a.upi_id}</CardDescription></div>
                  <div className="flex flex-wrap justify-end gap-1">{a.is_default ? <Badge variant="secondary">default</Badge> : null}<Badge variant={a.is_active ? "success" : "destructive"}>{a.is_active ? "active" : "inactive"}</Badge></div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p className="text-muted-foreground">{a.merchant_name} · {a.branch_name ? `${a.branch_name} branch` : "All branches"} · {a.use_dynamic_qr ? "Dynamic QR with amount" : "Static QR"}{a.service_count ? ` · ${a.service_count} service(s)` : ""}{a.bank_name ? ` · ${a.bank_name}${a.account_last4 ? ` ••${a.account_last4}` : ""}` : ""}</p>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" onClick={() => setPreview(a)}><QrCode /> Test QR</Button>
                  {canWrite ? <><Button size="sm" variant="ghost" onClick={() => setEditing(a)}>Edit</Button><Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Remove ${a.display_name}?`)) remove.mutate(a.id); }}>Remove</Button></> : null}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {canWrite && services.data?.length && active.length > 1 ? (
        <Card>
          <CardHeader><CardTitle>Service-specific accounts</CardTitle><CardDescription>Route a service&apos;s payments to a particular account, for example a separate account for therapies.</CardDescription></CardHeader>
          <CardContent><ul className="divide-y">{services.data.map((s) => <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-sm"><span>{s.name}</span><NativeSelect aria-label={`UPI account for ${s.name}`} className="w-64" defaultValue="" onChange={(e) => assign.mutate({ service_id: s.id, account: e.target.value || null })}><option value="">Branch / organization default</option>{active.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</NativeSelect></li>)}</ul></CardContent>
        </Card>
      ) : null}
      {editing ? <AccountSheet account={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); invalidate(); }} /> : null}
      {preview ? <PreviewDialog account={preview} onClose={() => setPreview(null)} /> : null}
    </div>
  );
}

function AccountSheet({ account, onClose, onSaved }: { account: UPIAccount | null; onClose: () => void; onSaved: () => void }) {
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => catalogService.branches() });
  const [form, setForm] = useState({
    display_name: account?.display_name ?? "", upi_id: account?.upi_id ?? "", merchant_name: account?.merchant_name ?? "", merchant_code: account?.merchant_code ?? "",
    branch_id: account?.branch_id ?? "", use_dynamic_qr: account?.use_dynamic_qr ?? true, static_qr_path: account?.static_qr_path ?? null as string | null,
    payment_instructions: account?.payment_instructions ?? "", bank_name: account?.bank_name ?? "", account_last4: account?.account_last4 ?? "",
    is_default: account?.is_default ?? false, is_active: account?.is_active ?? true,
  });
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, merchant_code: form.merchant_code || null, payment_instructions: form.payment_instructions || null, bank_name: form.bank_name || null, account_last4: form.account_last4 || null, branch_id: form.branch_id || undefined, clear_branch: account ? !form.branch_id : undefined };
      return account ? upiAccountsService.update(account.id, body) : upiAccountsService.create(body);
    },
    onSuccess: () => { toast.success(account ? "Account updated" : "Account added"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <SheetHeader><SheetTitle>{account ? `Edit ${account.display_name}` : "Add UPI account"}</SheetTitle><SheetDescription>Use the UPI ID linked to the clinic&apos;s current account. The merchant name appears in the customer&apos;s app.</SheetDescription></SheetHeader>
        <form id="upi-form" className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="upi-form">
          <Field label="Display name" htmlFor="u_name" hint="Only staff see this"><Input id="u_name" required minLength={2} placeholder="Main counter" value={form.display_name} onChange={set("display_name")} /></Field>
          <Field label="UPI ID" htmlFor="u_vpa"><Input id="u_vpa" required placeholder="clinic@okhdfcbank" value={form.upi_id} onChange={set("upi_id")} /></Field>
          <Field label="Merchant name (payee)" htmlFor="u_merchant" className="sm:col-span-2"><Input id="u_merchant" required minLength={2} value={form.merchant_name} onChange={set("merchant_name")} /></Field>
          <Field label="Branch" htmlFor="u_branch"><NativeSelect id="u_branch" value={form.branch_id} onChange={set("branch_id")}><option value="">All branches</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</NativeSelect></Field>
          <Field label="Merchant category code" htmlFor="u_mc" hint="Optional, 4 digits"><Input id="u_mc" inputMode="numeric" maxLength={4} value={form.merchant_code} onChange={set("merchant_code")} /></Field>
          <Field label="Bank name" htmlFor="u_bank"><Input id="u_bank" value={form.bank_name} onChange={set("bank_name")} /></Field>
          <Field label="Account last 4 digits" htmlFor="u_last4"><Input id="u_last4" inputMode="numeric" maxLength={4} value={form.account_last4} onChange={set("account_last4")} /></Field>
          <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm sm:col-span-2"><span>Generate a QR with the exact amount for every booking (recommended)</span><Switch checked={form.use_dynamic_qr} onCheckedChange={(v) => setForm({ ...form, use_dynamic_qr: v })} /></label>
          {!form.use_dynamic_qr ? <div className="sm:col-span-2"><ImageUpload label="Static QR image from your bank or UPI app" value={form.static_qr_path} onChange={(v) => setForm({ ...form, static_qr_path: v })} /></div> : null}
          <Field label="Payment instructions shown to customers" htmlFor="u_instr" className="sm:col-span-2"><Textarea id="u_instr" placeholder="Pay the exact amount. Keep the UTR from the success screen." value={form.payment_instructions} onChange={set("payment_instructions")} /></Field>
          <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Default for its scope</span><Switch checked={form.is_default} onCheckedChange={(v) => setForm({ ...form, is_default: v })} /></label>
          <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Active</span><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /></label>
        </form>
        <SheetFooter><Button type="button" variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" form="upi-form" disabled={save.isPending}>{account ? "Save" : "Add account"}</Button></SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function PreviewDialog({ account, onClose }: { account: UPIAccount; onClose: () => void }) {
  const preview = useQuery({ queryKey: ["upi-preview", account.id], queryFn: () => upiAccountsService.preview(account.id, 100) });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Test {account.display_name}</DialogTitle><DialogDescription>Scan with any UPI app to check the payee name. This asks for ₹1.00; you can cancel before paying.</DialogDescription></DialogHeader>
        {preview.data ? (
          <div className="flex flex-col items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preview.data.qr_data_url} alt="Test UPI QR" className="size-56 rounded-xl border bg-white p-2" />
            {preview.data.upi_uri ? <code className="w-full break-all rounded bg-muted p-2 text-[11px]">{preview.data.upi_uri}</code> : <p className="text-xs text-muted-foreground">Static QR: customers enter the amount themselves.</p>}
          </div>
        ) : <Skeleton className="h-56" />}
      </DialogContent>
    </Dialog>
  );
}
