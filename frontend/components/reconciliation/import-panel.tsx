"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { reconciliationService } from "@/services/reconciliation";
import { upiAccountsService } from "@/services/payments";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import type { ParserMapping, StatementImport, StatementPreview } from "@/types/reconciliation";

const DATE_FORMATS: [string, string][] = [
  ["%d/%m/%Y", "31/12/2026"], ["%d/%m/%y", "31/12/26"], ["%d-%m-%Y", "31-12-2026"], ["%d-%b-%Y", "31-Dec-2026"], ["%d %b %Y", "31 Dec 2026"],
  ["%d-%b-%y", "31-Dec-26"], ["%d.%m.%Y", "31.12.2026"], ["%Y-%m-%d", "2026-12-31"], ["%m/%d/%Y", "12/31/2026"],
];
const DELIMITERS: [string, string][] = [[",", "Comma"], [";", "Semicolon"], ["\t", "Tab"], ["|", "Pipe"]];
const STORAGE_KEY = "reconciliation.custom-mapping";

type Custom = { date: string; description: string; credit: string; debit: string; amount: string; type: string; reference: string; balance: string; dateFormat: string; delimiter: string; single: boolean };
const EMPTY: Custom = { date: "", description: "", credit: "", debit: "", amount: "", type: "", reference: "", balance: "", dateFormat: "%d/%m/%Y", delimiter: ",", single: false };

function loadCustom(): Custom {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<Custom>) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

/** Pick the separator that splits the first lines into the most columns. */
async function guessDelimiter(file: File, fallback: string): Promise<string> {
  try {
    const head = (await file.slice(0, 4096).text()).split(/\r?\n/).filter((l) => l.trim()).slice(0, 6);
    let best = fallback;
    let bestScore = 0;
    for (const [d] of DELIMITERS) {
      const score = Math.max(0, ...head.map((l) => l.split(d).length - 1));
      if (score > bestScore) { best = d; bestScore = score; }
    }
    return best;
  } catch {
    return fallback;
  }
}

/** The first preview row that looks like column titles: several non-empty, mostly non-numeric cells. */
function headerRow(preview: StatementPreview | null): string[] {
  for (const row of preview?.rows ?? []) {
    const cells = row.map((c) => c.trim()).filter(Boolean);
    if (cells.length >= 3 && cells.filter((c) => /[a-z]/i.test(c) && !/^\d/.test(c)).length >= cells.length * 0.7) return row.map((c) => c.trim());
  }
  return [];
}

export function ImportPanel({ onImported }: { onImported: (imp: StatementImport) => void }) {
  const queryClient = useQueryClient();
  const presets = useQuery({ queryKey: ["reconciliation-presets"], queryFn: reconciliationService.presets });
  const accounts = useQuery({ queryKey: ["upi-accounts"], queryFn: upiAccountsService.list });
  const [file, setFile] = useState<File | null>(null);
  const [parser, setParser] = useState("hdfc");
  const [account, setAccount] = useState("");
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [custom, setCustom] = useState<Custom>(loadCustom);
  const columns = useMemo(() => headerRow(preview), [preview]);
  const set = (patch: Partial<Custom>) => setCustom((c) => ({ ...c, ...patch }));

  const runPreview = useMutation({
    mutationFn: ({ f, delimiter }: { f: File; delimiter: string }) => reconciliationService.preview(f, delimiter),
    onSuccess: (data) => { setPreview(data); if (data.detected_preset) setParser(data.detected_preset); else setParser("custom"); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const mapping = (): Partial<ParserMapping> | null => {
    if (parser !== "custom") return null;
    return {
      date_column: custom.date, description_column: custom.description, reference_column: custom.reference || null, balance_column: custom.balance || null,
      ...(custom.single ? { amount_column: custom.amount, type_column: custom.type || null } : { credit_column: custom.credit, debit_column: custom.debit || null }),
      date_formats: [custom.dateFormat], delimiter: custom.delimiter,
    };
  };
  const customReady = parser !== "custom" || (custom.date && custom.description && (custom.single ? custom.amount : custom.credit));

  const doImport = useMutation({
    mutationFn: () => reconciliationService.importStatement(file!, parser, mapping(), account || null),
    onSuccess: (imp) => {
      if (parser === "custom") {
        try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(custom)); } catch { /* storage unavailable: mapping is simply not remembered */ }
      }
      toast.success(`${imp.total_rows} new credit(s) imported, ${imp.suggested_rows} suggested match(es)${imp.duplicate_rows ? `, ${imp.duplicate_rows} already imported` : ""}.`);
      ["reconciliation-imports", "reconciliation-transactions", "reconciliation-stats", "reconciliation-report"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));
      setFile(null);
      setPreview(null);
      onImported(imp);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const columnSelect = (id: string, label: string, value: string, key: keyof Custom, optional = false) => (
    <Field label={label} htmlFor={id}>
      <NativeSelect id={id} value={value} onChange={(e) => set({ [key]: e.target.value } as Partial<Custom>)}>
        <option value="">{optional ? "— none —" : "Choose a column"}</option>
        {columns.filter(Boolean).map((c) => <option key={c} value={c}>{c}</option>)}
      </NativeSelect>
    </Field>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Upload className="size-4" /> Import a bank statement</CardTitle>
        <CardDescription>Download the statement from your net-banking as CSV and upload it here. Only incoming credits are imported; re-uploading overlapping statements is safe.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Statement file (CSV)" htmlFor="stmt_file">
            <Input id="stmt_file" type="file" accept=".csv,text/csv,text/plain" onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              setPreview(null);
              if (f) void guessDelimiter(f, custom.delimiter).then((delimiter) => { set({ delimiter }); runPreview.mutate({ f, delimiter }); });
            }} />
          </Field>
          <Field label="Bank format" htmlFor="stmt_parser" hint={preview?.detected_preset ? "Detected from the file" : undefined}>
            <NativeSelect id="stmt_parser" value={parser} onChange={(e) => setParser(e.target.value)}>
              {presets.data?.map((p) => <option key={p.code} value={p.code}>{p.label}</option>)}
              <option value="custom">Other bank (map columns)</option>
            </NativeSelect>
          </Field>
          <Field label="Account (optional)" htmlFor="stmt_account">
            <NativeSelect id="stmt_account" value={account} onChange={(e) => setAccount(e.target.value)}>
              <option value="">Not specified</option>
              {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.display_name} · {a.upi_id}</option>)}
            </NativeSelect>
          </Field>
        </div>

        {parser === "custom" && file ? (
          <div className="space-y-3 rounded-xl border p-4" data-testid="custom-mapping">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Separator" htmlFor="map_delim">
                <NativeSelect id="map_delim" value={custom.delimiter} onChange={(e) => { set({ delimiter: e.target.value }); runPreview.mutate({ f: file, delimiter: e.target.value }); }}>
                  {DELIMITERS.map(([v, l]) => <option key={l} value={v}>{l}</option>)}
                </NativeSelect>
              </Field>
              <Field label="Date format" htmlFor="map_datefmt">
                <NativeSelect id="map_datefmt" value={custom.dateFormat} onChange={(e) => set({ dateFormat: e.target.value })}>
                  {DATE_FORMATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </NativeSelect>
              </Field>
              <label className="flex items-center gap-2 pb-2 text-sm"><Switch checked={custom.single} onCheckedChange={(v) => set({ single: v })} /> One amount column with Dr/Cr</label>
            </div>
            {columns.length === 0 ? <p className="text-sm text-destructive">Could not find a header row. Try another separator.</p> : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {columnSelect("map_date", "Date", custom.date, "date")}
                {columnSelect("map_desc", "Description / narration", custom.description, "description")}
                {custom.single ? columnSelect("map_amount", "Amount", custom.amount, "amount") : columnSelect("map_credit", "Credit / deposit", custom.credit, "credit")}
                {custom.single ? columnSelect("map_type", "Dr/Cr column", custom.type, "type", true) : columnSelect("map_debit", "Debit / withdrawal", custom.debit, "debit", true)}
                {columnSelect("map_ref", "Reference / UTR", custom.reference, "reference", true)}
                {columnSelect("map_bal", "Balance", custom.balance, "balance", true)}
              </div>
            )}
          </div>
        ) : null}

        {preview ? (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">First rows of {file?.name} ({preview.total_lines} lines)</p>
            <Table className="text-xs">
              <TableBody>
                {preview.rows.slice(0, 8).map((row, i) => <TableRow key={i}>{row.slice(0, 8).map((c, j) => <TableCell key={j} className="max-w-48 truncate py-1.5">{c}</TableCell>)}</TableRow>)}
              </TableBody>
            </Table>
          </div>
        ) : null}

        <Button onClick={() => doImport.mutate()} disabled={!file || !customReady || doImport.isPending} data-testid="import-statement">{doImport.isPending ? "Importing…" : "Import and suggest matches"}</Button>
      </CardContent>
    </Card>
  );
}
