import { cn } from "@/lib/utils";
import { STAFF_STATUS_LABELS, type StaffTicket } from "@/services/helpdesk";

export function StatusBadge({ status }: { status: StaffTicket["status"] }) {
  const tone = { open: "bg-sky-100 text-sky-900", pending_customer: "bg-amber-100 text-amber-900", resolved: "bg-emerald-100 text-emerald-900", closed: "bg-muted text-muted-foreground" }[status];
  return <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-medium", tone)}>{STAFF_STATUS_LABELS[status]}</span>;
}

export function PriorityBadge({ priority }: { priority: StaffTicket["priority"] }) {
  if (priority === "normal") return <span className="text-xs text-muted-foreground">Normal</span>;
  const tone = { low: "bg-muted text-muted-foreground", high: "bg-orange-100 text-orange-900", urgent: "bg-rose-100 text-rose-900" }[priority];
  return <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize", tone)}>{priority}</span>;
}

