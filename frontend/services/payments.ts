import { api } from "@/lib/api-client";
import { apiBase } from "@/lib/env";
import { credentialsMode, panelHeaders } from "@/lib/panel-session";
import type { ApiErrorBody, Page } from "@/types/api";
import type { Checkout, Coupon, Payment, PaymentDetail, PaymentStats, QRPreview, UPIAccount } from "@/types/payment";

type Body = Record<string, unknown>;

export const upiAccountsService = {
  list: () => api.get<UPIAccount[]>("/upi-accounts"),
  create: (body: Body) => api.post<UPIAccount>("/upi-accounts", body),
  update: (id: string, body: Body) => api.patch<UPIAccount>(`/upi-accounts/${id}`, body),
  remove: (id: string) => api.delete<ApiErrorBody>(`/upi-accounts/${id}`),
  preview: (id: string, amount_paise = 100) => api.get<QRPreview>(`/upi-accounts/${id}/preview`, { searchParams: { amount_paise } }),
  assign: (service_id: string, upi_account_id: string | null) => api.post<ApiErrorBody>("/upi-accounts/assign", { service_id, upi_account_id }),
};

export const paymentsService = {
  list: (params: { status?: string; method?: string; search?: string; appointment_id?: string; customer_id?: string; page?: number; page_size?: number }) =>
    api.get<Page<Payment>>("/payments", { searchParams: params }),
  get: (id: string) => api.get<PaymentDetail>(`/payments/${id}`),
  create: (body: { appointment_id: string; kind: string; method: string; utr?: string; notes?: string }) => api.post<PaymentDetail>("/payments", body),
  checkout: (id: string) => api.get<Checkout>(`/payments/${id}/checkout`),
  stats: () => api.get<PaymentStats>("/admin/payments/stats"),
  queue: (params: { status?: string; page?: number; page_size?: number } = {}) => api.get<Page<Payment>>("/admin/payments/queue", { searchParams: params }),
  review: (id: string) => api.post<PaymentDetail>(`/admin/payments/${id}/review`),
  verify: (id: string, body: { bank_credit_confirmed: boolean; verified_amount_paise: number; amount_mismatch_reason?: string; notes?: string }) =>
    api.post<PaymentDetail>(`/admin/payments/${id}/verify`, body),
  reject: (id: string, body: { reason: string; notes?: string }) => api.post<PaymentDetail>(`/admin/payments/${id}/reject`, body),
  note: (id: string, notes: string) => api.post<PaymentDetail>(`/admin/payments/${id}/notes`, { notes }),
  screenshotUrl: (paymentId: string, submissionId: string) => `${apiBase}/payments/${paymentId}/submissions/${submissionId}/screenshot`,
  mine: () => api.get<Payment[]>("/customer/payments"),
};

export const couponsService = {
  list: () => api.get<Coupon[]>("/coupons"),
  create: (body: Body) => api.post<Coupon>("/coupons", body),
  update: (id: string, body: Body) => api.patch<Coupon>(`/coupons/${id}`, body),
  remove: (id: string) => api.delete<ApiErrorBody>(`/coupons/${id}`),
};

export const publicPayments = {
  checkout: (slug: string, reference: string, access_token: string | null) =>
    api.get<Checkout | null>(`/public/organizations/${slug}/appointments/${reference}/payment`, { searchParams: { access_token: access_token ?? undefined } }),
  submit: (slug: string, reference: string, access_token: string | null, data: { utr: string; transaction_reference?: string; paid_at?: string; payer_upi_id?: string; notes?: string; screenshot?: File | null }) => {
    const form = new FormData();
    form.append("utr", data.utr);
    if (data.transaction_reference) form.append("transaction_reference", data.transaction_reference);
    if (data.paid_at) form.append("paid_at", data.paid_at);
    if (data.payer_upi_id) form.append("payer_upi_id", data.payer_upi_id);
    if (data.notes) form.append("notes", data.notes);
    if (data.screenshot) form.append("screenshot", data.screenshot);
    // One UTR for one appointment is one submission: retries with the same key return the first answer.
    return api.post<Checkout>(`/public/organizations/${slug}/appointments/${reference}/payment/submit`, form, {
      searchParams: { access_token: access_token ?? undefined }, headers: { "Idempotency-Key": `utr:${reference}:${data.utr.replace(/[^A-Za-z0-9]/g, "")}`.slice(0, 100) } });
  },
};

/** Fetch a private file with the session (and organization header) and return an object URL for <img>. */
export async function fetchPrivateObjectUrl(url: string, organizationId?: string | null): Promise<string> {
  const res = await fetch(url, { credentials: credentialsMode(), headers: { ...(organizationId ? { "X-Organization-Id": organizationId } : {}), ...panelHeaders() } });
  if (!res.ok) throw new Error(`Could not load file (${res.status})`);
  return URL.createObjectURL(await res.blob());
}
