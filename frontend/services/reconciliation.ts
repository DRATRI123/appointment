import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { ApiErrorBody, Page } from "@/types/api";
import type { BankTransaction, MatchCandidate, ParserMapping, ParserPreset, ReconciliationStats, StatementImport, StatementPreview, UnmatchedReport } from "@/types/reconciliation";

export const reconciliationService = {
  presets: () => api.get<ParserPreset[]>("/reconciliation/presets"),
  preview: (file: File, delimiter = ",") => {
    const form = new FormData();
    form.append("file", file);
    form.append("delimiter", delimiter);
    return api.post<StatementPreview>("/reconciliation/preview", form);
  },
  imports: () => api.get<StatementImport[]>("/reconciliation/imports"),
  importStatement: (file: File, parser_code: string, mapping?: Partial<ParserMapping> | null, upi_account_id?: string | null) => {
    const form = new FormData();
    form.append("file", file);
    form.append("parser_code", parser_code);
    if (mapping) form.append("mapping", JSON.stringify(mapping));
    if (upi_account_id) form.append("upi_account_id", upi_account_id);
    return api.post<StatementImport>("/reconciliation/imports", form);
  },
  deleteImport: (id: string) => api.delete<ApiErrorBody>(`/reconciliation/imports/${id}`),
  stats: () => api.get<ReconciliationStats>("/reconciliation/stats"),
  rerun: () => api.post<ApiErrorBody>("/reconciliation/suggest"),
  transactions: (params: { status?: string; import_id?: string; search?: string; from_date?: string; to_date?: string; page?: number; page_size?: number }) =>
    api.get<Page<BankTransaction>>("/reconciliation/transactions", { searchParams: params }),
  candidates: (id: number) => api.get<MatchCandidate[]>(`/reconciliation/transactions/${id}/candidates`),
  match: (id: number, payment_id: string, notes?: string) => api.post<BankTransaction>(`/reconciliation/transactions/${id}/match`, { payment_id, notes }),
  unmatch: (id: number, reason?: string) => api.post<BankTransaction>(`/reconciliation/transactions/${id}/unmatch`, { reason }),
  ignore: (id: number, reason: string) => api.post<BankTransaction>(`/reconciliation/transactions/${id}/ignore`, { reason }),
  restore: (id: number) => api.post<BankTransaction>(`/reconciliation/transactions/${id}/restore`),
  report: (params: { from_date?: string; to_date?: string } = {}) => api.get<UnmatchedReport>("/reconciliation/report", { searchParams: params }),
  reportCsvUrl: () => `${apiBase}/reconciliation/report.csv`,
};
