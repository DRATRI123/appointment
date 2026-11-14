"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, Download, Landmark, RefreshCw, Trash2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { reconciliationService } from "@/services/reconciliation";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { ImportPanel } from "@/components/reconciliation/import-panel";
import { IgnoreDialog, MatchDialog } from "@/components/reconciliation/match-dialog";
import { PaymentSheet } from "@/components/payments/payment-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Segmented } from "@/components/ui/segmented";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { downloadPrivateFile } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import { formatDate, formatDateTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { PAYMENT_STATUS_LABEL, type PaymentStatus } from "@/types/payment";
import { MATCH_STATUS_LABEL, MATCH_STATUS_VARIANT, type BankTransaction } from "@/types/reconciliation";

const KEYS = ["reconciliation-transactions", "reconciliation-stats", "reconciliation-imports", "reconciliation-report", "payment", "payments"];
const FILTERS: [string, string][] = [["unmatched,suggested", "Needs review"], ["suggested", "Suggested"], ["matched", "Matched"], ["ignored", "Ignored"], ["", "All"]];
const bankDate = (d: string) => formatDate(d, "UTC");

export default function ReconciliationPage() {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("transactions");
  const [filter, setFilter] = useState("unmatched,suggested");
  const [importId, setImportId] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [matching, setMatching] = useState<BankTransaction | null>(null);
  const [ignoring, setIgnoring] = useState<BankTransaction | null>(null);
  const [payment, setPayment] = useState<string | null>(null);
  const allowed = hasPermission("reconciliation:manage");
  const refresh = () => KEYS.forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));

  const stats = useQuery({ queryKey: ["reconciliation-stats", orgId], queryFn: reconciliationService.stats, enabled: !!orgId && allowed });
  const imports = useQuery({ queryKey: ["reconciliation-imports", orgId], queryFn: reconciliationService.imports, enabled: !!orgId && allowed });
  const txns = useQuery({
    queryKey: ["reconciliation-transactions", orgId, filter, importId, search, page],
    queryFn: () => reconciliationService.transactions({ status: filter || undefined, import_id: importId || undefined, search: search || undefined, page, page_size: 25 }),
    enabled: !!orgId && allowed,
  });
  const report = useQuery({ queryKey: ["reconciliation-report", orgId], queryFn: () => reconciliationService.report(), enabled: !!orgId && allowed && tab === "report" });

  const confirm = useMutation({ mutationFn: (t: BankTransaction) => reconciliationService.match(t.id, t.matched_payment_id!), onSuccess: () => { toast.success("Match confirmed"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const unmatch = useMutation({ mutationFn: (t: BankTransaction) => reconciliationService.unmatch(t.id), onSuccess: () => { toast.success("Unmatched"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const restore = useMutation({ mutationFn: (t: BankTransaction) => reconciliationService.restore(t.id), onSuccess: () => { toast.success("Restored"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const rerun = useMutation({ mutationFn: reconciliationService.rerun, onSuccess: (r) => { toast.success(r.detail ?? "Done"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: (id: string) => reconciliationService.deleteImport(id), onSuccess: () => { toast.success("Statement removed"); setImportId(""); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const download = useMutation({ mutationFn: () => downloadPrivateFile(reconciliationService.reportCsvUrl(), "unmatched-report.csv", orgId), onError: (e) => toast.error(errorMessage(e)) });

  if (!allowed) return <EmptyState icon={Landmark} title="No access" body="Bank reconciliation needs the reconciliation permission (accountants and owners have it)." />;
  const s = stats.data;
  const cards: [string, React.ReactNode, string?][] = [
    ["Credits to review", s ? s.unmatched + s.suggested : "—", s ? formatPaise(s.unmatched_amount_paise) : undefined],
    ["Suggested matches", s ? s.suggested : "—"],
    ["Matched credits", s ? s.matched : "—"],
    ["Verified payments with no bank credit", s ? s.verified_without_bank_match : "—", "Check these against the bank"],
  ];
  const pages = txns.data ? Math.max(1, Math.ceil(txns.data.meta.total / txns.data.meta.page_size)) : 1;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Bank reconciliation" description="Match the credits in your bank statement to customer payments. Matches are evidence for verifiers; they never approve a payment by themselves."
        actions={<Button variant="outline" onClick={() => rerun.mutate()} disabled={rerun.isPending}><RefreshCw /> Refresh suggestions</Button>} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([label, value, sub]) => <Card key={label} className="gap-1 py-4"><CardHeader><CardDescription>{label}</CardDescription></CardHeader><CardContent className="text-xl font-semibold">{value}{sub ? <span className="block text-xs font-normal text-muted-foreground">{sub}</span> : null}</CardContent></Card>)}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <div className="max-w-full overflow-x-auto">
          <TabsList>
            <TabsTrigger value="transactions">Bank credits</TabsTrigger>
            <TabsTrigger value="import">Import statement</TabsTrigger>
            <TabsTrigger value="statements">Statements</TabsTrigger>
            <TabsTrigger value="report">Unmatched report</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="transactions" className="space-y-4 pt-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-full overflow-x-auto">
              <Segmented label="Show" value={filter} onChange={(v) => { setPage(1); setFilter(v); }} options={FILTERS} />
            </div>
            <Input className="lg:w-80" placeholder="Search UTR, narration or amount" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
          </div>
          {importId ? <p className="text-sm">Showing one statement. <button className="underline" onClick={() => setImportId("")}>Show all</button></p> : null}
          {txns.isLoading ? <Skeleton className="h-64" /> : txns.data?.data.length === 0 ? (
            <EmptyState icon={Landmark} title={filter.includes("unmatched") ? "Nothing to review" : "No bank credits here"} body="Import a statement to see incoming credits and suggested matches." action={<Button onClick={() => setTab("import")}>Import statement</Button>} />
          ) : (
            <>
              <Table>
                <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Amount</TableHead><TableHead>Bank details</TableHead><TableHead>Match</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                <TableBody>
                  {txns.data?.data.map((t) => (
                    <TableRow key={t.id} data-testid="bank-row">
                      <TableCell className="whitespace-nowrap">{bankDate(t.transaction_date)}</TableCell>
                      <TableCell className="whitespace-nowrap font-medium">{formatPaise(t.amount_paise)}</TableCell>
                      <TableCell className="max-w-96 text-xs">
                        {t.utr ? <span className="font-mono">UTR {t.utr}</span> : <span className="text-muted-foreground">No UTR found</span>}
                        {t.duplicate_utr ? <span className="ml-1 inline-flex items-center gap-0.5 text-destructive"><AlertTriangle className="size-3" />UTR appears twice</span> : null}
                        {t.payer_vpa ? <span className="ml-2 text-muted-foreground">{t.payer_vpa}</span> : null}
                        <span className="block truncate text-muted-foreground" title={t.description ?? ""}>{t.description}</span>
                      </TableCell>
                      <TableCell className="text-xs">
                        <Badge variant={MATCH_STATUS_VARIANT[t.match_status]}>{MATCH_STATUS_LABEL[t.match_status]}{t.match_status === "suggested" && t.match_confidence ? ` · ${t.match_confidence}%` : ""}</Badge>
                        {t.matched_payment_reference ? (
                          <button type="button" className="mt-1 block text-left underline-offset-2 hover:underline" onClick={() => setPayment(t.matched_payment_id)}>
                            {t.matched_customer_name} <span className="font-mono text-muted-foreground">{t.matched_payment_reference.slice(-10)}</span>
                            <span className="block text-muted-foreground">{PAYMENT_STATUS_LABEL[t.matched_payment_status as PaymentStatus] ?? t.matched_payment_status}</span>
                          </button>
                        ) : null}
                        {t.match_status === "ignored" && t.notes ? <span className="mt-1 block text-muted-foreground">{t.notes}</span> : null}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {t.match_status === "suggested" ? <><Button size="sm" onClick={() => confirm.mutate(t)} disabled={confirm.isPending} data-testid="confirm-suggestion">Confirm</Button><Button size="sm" variant="ghost" onClick={() => unmatch.mutate(t)}>Not this</Button></> : null}
                          {t.match_status === "unmatched" ? <><Button size="sm" variant="outline" onClick={() => setMatching(t)} data-testid="find-payment">Find payment</Button><Button size="sm" variant="ghost" onClick={() => setIgnoring(t)}>Ignore</Button></> : null}
                          {t.match_status === "matched" ? <><Button size="sm" variant="outline" onClick={() => setPayment(t.matched_payment_id)}>Open payment</Button><Button size="sm" variant="ghost" onClick={() => unmatch.mutate(t)}>Unmatch</Button></> : null}
                          {t.match_status === "ignored" ? <Button size="sm" variant="ghost" onClick={() => restore.mutate(t)}>Restore</Button> : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{txns.data?.meta.total} credits</span><div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div></div>
            </>
          )}
        </TabsContent>

        <TabsContent value="import" className="pt-4">
          <ImportPanel onImported={(imp) => { setImportId(imp.id); setFilter("unmatched,suggested"); setPage(1); setTab("transactions"); }} />
        </TabsContent>

        <TabsContent value="statements" className="pt-4">
          {imports.isLoading ? <Skeleton className="h-48" /> : imports.data?.length === 0 ? <EmptyState icon={Landmark} title="No statements yet" body="Imported statements are listed here with their match progress." /> : (
            <Table>
              <TableHeader><TableRow><TableHead>Uploaded</TableHead><TableHead>File</TableHead><TableHead>Period</TableHead><TableHead>Credits</TableHead><TableHead>Matched</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {imports.data?.map((i) => (
                  <TableRow key={i.id} data-testid="import-row">
                    <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(i.created_at)}<span className="block text-xs">{i.uploaded_by_name}</span></TableCell>
                    <TableCell className="max-w-64"><span className="block truncate">{i.file_name}</span><span className="text-xs text-muted-foreground">{i.parser_code}{i.upi_account_name ? ` · ${i.upi_account_name}` : ""}</span></TableCell>
                    <TableCell className="whitespace-nowrap text-xs">{i.statement_from ? `${bankDate(i.statement_from)} – ${bankDate(i.statement_to!)}` : "—"}</TableCell>
                    <TableCell className="text-xs">{i.total_rows} new{i.duplicate_rows ? <span className="block text-muted-foreground">{i.duplicate_rows} already imported</span> : null}{i.skipped_rows ? <span className="block text-destructive" title={i.skipped?.map((s) => `line ${s.line}: ${s.error}`).join("\n")}>{i.skipped_rows} unreadable</span> : null}</TableCell>
                    <TableCell className="text-xs">{i.matched_rows} / {i.total_rows}{i.suggested_rows ? <span className="block text-muted-foreground">{i.suggested_rows} suggested</span> : null}{i.status === "reconciled" ? <Badge variant="success" className="mt-1">Done</Badge> : null}</TableCell>
                    <TableCell><div className="flex justify-end gap-1"><Button size="sm" variant="outline" onClick={() => { setImportId(i.id); setFilter(""); setTab("transactions"); }}>View</Button><Button size="icon" variant="ghost" aria-label="Delete statement" onClick={() => remove.mutate(i.id)}><Trash2 /></Button></div></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="report" className="space-y-4 pt-4">
          <div className="flex justify-end"><Button variant="outline" onClick={() => download.mutate()} disabled={download.isPending}><Download /> Download CSV</Button></div>
          {report.isLoading || !report.data ? <Skeleton className="h-48" /> : (
            <div className="grid gap-4 xl:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Bank credits without a payment</CardTitle><CardDescription>Money arrived but no booking payment is matched. Find the payment or ignore the credit.</CardDescription></CardHeader>
                <CardContent>
                  {report.data.bank_credits.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> : (
                    <ul className="divide-y text-sm">{report.data.bank_credits.map((t) => <li key={t.id} className="flex flex-wrap items-center gap-2 py-2"><span className="w-24 text-muted-foreground">{bankDate(t.transaction_date)}</span><span className="font-medium">{formatPaise(t.amount_paise)}</span><span className="font-mono text-xs">{t.utr}</span><Button size="sm" variant="ghost" className="ml-auto" onClick={() => setMatching(t)}>Find payment</Button></li>)}</ul>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>Verified payments without a bank credit</CardTitle><CardDescription>Approved by staff, but no imported statement line is matched to them yet.</CardDescription></CardHeader>
                <CardContent>
                  {report.data.payments.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> : (
                    <ul className="divide-y text-sm">{report.data.payments.map((p) => <li key={p.payment_id} className="flex flex-wrap items-center gap-2 py-2"><span className="w-24 text-muted-foreground">{p.verified_at ? formatDate(p.verified_at) : "—"}</span><span className="font-medium">{formatPaise(p.verified_amount_paise ?? p.amount_paise)}</span><span>{p.customer_name}</span><span className="font-mono text-xs">{p.latest_utr}</span><Button size="sm" variant="ghost" className="ml-auto" onClick={() => setPayment(p.payment_id)}>Open</Button></li>)}</ul>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {matching ? <MatchDialog txn={matching} onClose={() => setMatching(null)} onDone={() => { setMatching(null); refresh(); }} /> : null}
      {ignoring ? <IgnoreDialog txn={ignoring} onClose={() => setIgnoring(null)} onDone={() => { setIgnoring(null); refresh(); }} /> : null}
      {payment ? <PaymentSheet id={payment} onClose={() => { setPayment(null); refresh(); }} /> : null}
    </div>
  );
}
