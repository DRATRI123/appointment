import { Badge } from "@/components/ui/badge";
import { PAYMENT_STATUS_LABEL, PAYMENT_STATUS_VARIANT, type PaymentStatus } from "@/types/payment";

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  return <Badge variant={PAYMENT_STATUS_VARIANT[status]} data-testid="payment-status">{PAYMENT_STATUS_LABEL[status]}</Badge>;
}
