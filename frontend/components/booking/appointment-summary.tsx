import { Badge } from "@/components/ui/badge";
import { formatDateLong, formatTime } from "@/lib/format";
import { formatPaise } from "@/lib/utils";
import { STATUS_LABEL, STATUS_VARIANT, type Appointment } from "@/types/booking";

export function StatusBadge({ status }: { status: Appointment["status"] }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function AppointmentSummary({ appt, showCustomer = false }: { appt: Appointment; showCustomer?: boolean }) {
  const due = appt.advance_due_paise - appt.paid_amount_paise;
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      <div><dt className="text-muted-foreground">When</dt><dd className="font-medium">{formatDateLong(appt.start_at, appt.timezone)} · {formatTime(appt.start_at, appt.timezone)}–{formatTime(appt.end_at, appt.timezone)}</dd></div>
      <div><dt className="text-muted-foreground">Status</dt><dd><StatusBadge status={appt.status} /></dd></div>
      <div><dt className="text-muted-foreground">Service</dt><dd>{appt.service_name}</dd></div>
      <div><dt className="text-muted-foreground">Professional</dt><dd>{appt.professional_name}</dd></div>
      <div><dt className="text-muted-foreground">Branch</dt><dd>{appt.branch_name}</dd></div>
      <div><dt className="text-muted-foreground">Reference</dt><dd className="font-mono text-xs">{appt.reference}</dd></div>
      {showCustomer ? <div><dt className="text-muted-foreground">Customer</dt><dd>{appt.customer.full_name} <span className="text-muted-foreground">{appt.customer.mobile ?? appt.customer.email}</span></dd></div> : null}
      <div><dt className="text-muted-foreground">Amount</dt><dd>{appt.total_amount_paise === 0 ? "Free" : formatPaise(appt.total_amount_paise)}{appt.discount_paise ? <span className="ml-1 text-xs text-muted-foreground">(saved {formatPaise(appt.discount_paise)})</span> : null}</dd></div>
      <div><dt className="text-muted-foreground">Payable now</dt><dd>{due > 0 ? <span className="font-semibold">{formatPaise(due)}</span> : appt.paid_amount_paise ? `Paid ${formatPaise(appt.paid_amount_paise)}` : "Nothing due now"}</dd></div>
      {appt.customer_notes ? <div className="sm:col-span-2"><dt className="text-muted-foreground">Notes</dt><dd>{appt.customer_notes}</dd></div> : null}
    </dl>
  );
}
