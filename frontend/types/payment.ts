import type { BankEvidence } from "@/types/reconciliation";
import type { RefundSummary } from "@/types/refund";

export type PaymentStatus =
  | "initiated" | "awaiting_payment" | "submitted" | "under_review" | "verified" | "rejected" | "expired" | "cancelled" | "refund_requested" | "refund_processed";

export interface UPIAccount {
  id: string;
  display_name: string;
  upi_id: string;
  merchant_name: string;
  merchant_code: string | null;
  static_qr_path: string | null;
  use_dynamic_qr: boolean;
  payment_instructions: string | null;
  bank_name: string | null;
  account_last4: string | null;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
  branch_id: string | null;
  branch_name: string | null;
  service_count: number;
  created_at: string;
}

export interface QRPreview { upi_uri: string | null; qr_data_url: string; is_static: boolean; amount_paise: number | null }

export interface Payment {
  id: string;
  reference: string;
  status: PaymentStatus;
  kind: "advance" | "balance" | "full";
  method: "upi_qr" | "cash" | "bank_transfer" | "pay_at_clinic" | "free";
  currency: string;
  amount_paise: number;
  verified_amount_paise: number | null;
  expires_at: string | null;
  submitted_at: string | null;
  verified_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  appointment_id: string | null;
  appointment_reference: string | null;
  appointment_start_at: string | null;
  appointment_timezone: string | null;
  appointment_status: string | null;
  service_name: string | null;
  branch_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  customer_mobile: string | null;
  upi_account_id: string | null;
  upi_account_name: string | null;
  upi_id: string | null;
  latest_utr: string | null;
  duplicate_utr_flag: boolean;
  created_at: string;
  organization_name?: string;
  organization_slug?: string;
}

export interface Submission {
  id: string;
  utr: string | null;
  transaction_reference: string | null;
  payer_upi_id: string | null;
  payer_name: string | null;
  paid_at: string | null;
  claimed_amount_paise: number | null;
  has_screenshot: boolean;
  notes: string | null;
  is_superseded: boolean;
  created_at: string;
}

export interface VerificationLog {
  action: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  bank_credit_confirmed: boolean | null;
  actor_name: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface PaymentDetail extends Payment {
  submissions: Submission[];
  logs: VerificationLog[];
  notes: string | null;
  bank_evidence: BankEvidence[];
  refund: RefundSummary | null;
}

export interface PaymentStats {
  awaiting_payment: number;
  submitted: number;
  under_review: number;
  verified_today: number;
  rejected_today: number;
  pending_amount_paise: number;
  verified_amount_today_paise: number;
}

export interface CheckoutUPI {
  account_name: string;
  upi_id: string;
  merchant_name: string;
  instructions: string | null;
  is_static: boolean;
  upi_uri: string | null;
  qr_data_url: string | null;
  static_qr_url: string | null;
  app_links: Record<"any" | "gpay" | "phonepe" | "paytm" | "bhim", string>;
}

export interface Checkout {
  payment: Payment;
  upi: CheckoutUPI | null;
  can_submit: boolean;
  latest_submission: Submission | null;
  message: string | null;
}

export interface Coupon {
  id: string;
  code: string;
  description: string | null;
  discount_type: "percent" | "flat";
  discount_value: number;
  max_discount_paise: number | null;
  min_amount_paise: number | null;
  valid_from: string | null;
  valid_to: string | null;
  max_redemptions: number | null;
  per_customer_limit: number | null;
  service_ids: string[] | null;
  is_active: boolean;
  redemptions: number;
  created_at: string;
}

export const PAYMENT_STATUS_LABEL: Record<PaymentStatus, string> = {
  initiated: "Initiated", awaiting_payment: "Awaiting payment", submitted: "Submitted", under_review: "Under review", verified: "Verified",
  rejected: "Rejected", expired: "Expired", cancelled: "Cancelled", refund_requested: "Refund requested", refund_processed: "Refunded",
};

export const PAYMENT_STATUS_VARIANT: Record<PaymentStatus, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  initiated: "outline", awaiting_payment: "outline", submitted: "warning", under_review: "warning", verified: "success",
  rejected: "destructive", expired: "outline", cancelled: "outline", refund_requested: "secondary", refund_processed: "secondary",
};

export const METHOD_LABEL: Record<Payment["method"], string> = { upi_qr: "UPI QR", cash: "Cash", bank_transfer: "Bank transfer", pay_at_clinic: "Pay at clinic", free: "Free" };
