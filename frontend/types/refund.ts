export type RefundStatus = "requested" | "approved" | "rejected" | "processed" | "cancelled";
export type RefundMethod = "upi" | "bank_transfer" | "cash";

export interface Refund {
  id: string;
  reference: string;
  status: RefundStatus;
  amount_paise: number;
  reason: string | null;
  rejection_reason: string | null;
  refund_method: RefundMethod | null;
  refund_reference: string | null;
  destination: string | null;
  has_proof: boolean;
  notes: string | null;
  payment_id: string;
  payment_reference: string;
  payment_method: string;
  payment_verified_amount_paise: number | null;
  appointment_id: string | null;
  appointment_reference: string | null;
  appointment_status: string | null;
  customer_id: string | null;
  customer_name: string | null;
  customer_mobile: string | null;
  requested_by_name: string | null;
  approved_by_name: string | null;
  processed_by_name: string | null;
  requested_at: string | null;
  approved_at: string | null;
  processed_at: string | null;
  rejected_at: string | null;
  created_at: string;
}

export interface RefundSummary {
  payment_id: string;
  verified_amount_paise: number;
  refunded_paise: number;
  pending_paise: number;
  refundable_paise: number;
  suggested_paise: number;
  suggestion_reason: string | null;
  refunds: Refund[];
}

export interface RefundStats {
  requested: number;
  approved: number;
  processed_this_month: number;
  pending_amount_paise: number;
  processed_amount_this_month_paise: number;
}

export interface MyRefund {
  id: string;
  reference: string;
  status: RefundStatus;
  amount_paise: number;
  payment_reference: string;
  appointment_reference: string | null;
  refund_method: RefundMethod | null;
  refund_reference: string | null;
  rejection_reason: string | null;
  requested_at: string | null;
  processed_at: string | null;
  organization_name: string;
}

export const REFUND_STATUS_LABEL: Record<RefundStatus, string> = {
  requested: "Requested", approved: "Approved, not yet sent", rejected: "Rejected", processed: "Refunded", cancelled: "Withdrawn",
};

export const REFUND_STATUS_VARIANT: Record<RefundStatus, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  requested: "warning", approved: "secondary", rejected: "destructive", processed: "success", cancelled: "outline",
};

export const REFUND_METHOD_LABEL: Record<RefundMethod, string> = { upi: "UPI", bank_transfer: "Bank transfer", cash: "Cash" };
