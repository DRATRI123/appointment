import { Badge } from "@/components/ui/badge";
import { REFUND_STATUS_LABEL, REFUND_STATUS_VARIANT, type RefundStatus } from "@/types/refund";

export function RefundStatusBadge({ status }: { status: RefundStatus }) {
  return <Badge variant={REFUND_STATUS_VARIANT[status]} data-testid="refund-status">{REFUND_STATUS_LABEL[status]}</Badge>;
}
