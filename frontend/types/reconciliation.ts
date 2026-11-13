export type MatchStatus = "unmatched" | "suggested" | "matched" | "ignored";

export interface ParserMapping {
  date_column: string;
  description_column: string;
  credit_column?: string | null;
  debit_column?: string | null;
  amount_column?: string | null;
  type_column?: string | null;
  reference_column?: string | null;
  value_date_column?: string | null;
  balance_column?: string | null;
  date_formats?: string[];
  delimiter?: string;
}

export interface ParserPreset { code: string; label: string; mapping: ParserMapping }

export interface StatementPreview { rows: string[][]; total_lines: number; detected_preset: string | null }

export interface StatementImport {
  id: string;
  file_name: string;
  parser_code: string;
  status: "uploaded" | "parsed" | "failed" | "reconciled";
  statement_from: string | null;
  statement_to: string | null;
  total_rows: number;
  matched_rows: number;
  suggested_rows: number;
  duplicate_rows: number;
  skipped_rows: number;
  skipped: { line: number; error: string }[] | null;
  upi_account_name: string | null;
  uploaded_by_name: string | null;
  error_message: string | null;
  created_at: string;
}

export interface BankTransaction {
  id: number;
  import_id: string;
  transaction_date: string;
  value_date: string | null;
  description: string | null;
  utr: string | null;
  payer_vpa: string | null;
  amount_paise: number;
  direction: "credit" | "debit";
  balance_paise: number | null;
  match_status: MatchStatus;
  match_confidence: number | null;
  matched_payment_id: string | null;
  matched_payment_reference: string | null;
  matched_payment_status: string | null;
  matched_customer_name: string | null;
  matched_by_name: string | null;
  matched_at: string | null;
  notes: string | null;
  duplicate_utr: boolean;
}

export interface MatchCandidate {
  payment_id: string;
  payment_reference: string;
  payment_status: string;
  amount_paise: number;
  customer_name: string | null;
  appointment_reference: string | null;
  latest_utr: string | null;
  submitted_at: string | null;
  score: number;
  reasons: string[];
}

export interface ReconciliationStats {
  unmatched: number;
  suggested: number;
  matched: number;
  ignored: number;
  unmatched_amount_paise: number;
  verified_without_bank_match: number;
}

export interface UnmatchedPayment {
  payment_id: string;
  payment_reference: string;
  status: string;
  method: string;
  amount_paise: number;
  verified_amount_paise: number | null;
  latest_utr: string | null;
  customer_name: string | null;
  verified_at: string | null;
  submitted_at: string | null;
}

export interface UnmatchedReport { bank_credits: BankTransaction[]; payments: UnmatchedPayment[] }

export interface BankEvidence {
  transaction_id: number;
  transaction_date: string;
  amount_paise: number;
  utr: string | null;
  description: string | null;
  match_status: MatchStatus;
  matched_to_this_payment: boolean;
  matched_payment_reference: string | null;
}

export const MATCH_STATUS_LABEL: Record<MatchStatus, string> = { unmatched: "Unmatched", suggested: "Suggested", matched: "Matched", ignored: "Ignored" };
export const MATCH_STATUS_VARIANT: Record<MatchStatus, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  unmatched: "destructive", suggested: "warning", matched: "success", ignored: "outline",
};
