import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import type { Page } from "@/types/api";
import type { MyRefund, Refund, RefundMethod, RefundStats, RefundSummary } from "@/types/refund";

export const refundsService = {
  list: (params: { status?: string; search?: string; page?: number; page_size?: number }) => api.get<Page<Refund>>("/refunds", { searchParams: params }),
  stats: () => api.get<RefundStats>("/refunds/stats"),
  get: (id: string) => api.get<Refund>(`/refunds/${id}`),
  forPayment: (paymentId: string) => api.get<RefundSummary>(`/refunds/for-payment/${paymentId}`),
  request: (body: { payment_id: string; amount_paise?: number; reason: string; destination?: string; refund_method?: RefundMethod }) => api.post<Refund>("/refunds", body),
  approve: (id: string, notes?: string) => api.post<Refund>(`/refunds/${id}/approve`, { notes }),
  reject: (id: string, reason: string) => api.post<Refund>(`/refunds/${id}/reject`, { reason }),
  cancel: (id: string, notes?: string) => api.post<Refund>(`/refunds/${id}/cancel`, { notes }),
  process: (id: string, body: { refund_method: RefundMethod; refund_reference?: string; destination?: string; processed_at?: string; money_sent_confirmed: boolean; notes?: string }) =>
    api.post<Refund>(`/refunds/${id}/process`, body),
  uploadProof: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<Refund>(`/refunds/${id}/proof`, form);
  },
  proofUrl: (id: string) => `${apiBase}/refunds/${id}/proof`,
  mine: () => api.get<MyRefund[]>("/customer/refunds"),
};
