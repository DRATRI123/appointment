import { AlertTriangle, CheckCircle2, CircleDashed, CircleOff, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "@/services/platform-integrations";

const STYLE: Record<ConnectionStatus, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  connected: { label: "Connected", className: "bg-success/15 text-success-ink", Icon: CheckCircle2 },
  error: { label: "Needs attention", className: "bg-destructive/15 text-destructive-ink", Icon: AlertTriangle },
  untested: { label: "Not tested yet", className: "bg-warning/20 text-foreground", Icon: HelpCircle },
  not_configured: { label: "Not set up", className: "bg-muted text-muted-foreground", Icon: CircleDashed },
  disabled: { label: "Switched off", className: "bg-muted text-muted-foreground", Icon: CircleOff },
};

/** "Connected" is only ever shown after a real, successful connection test with the saved settings. */
export function StatusPill({ status, className }: { status: ConnectionStatus; className?: string }) {
  const s = STYLE[status] ?? STYLE.not_configured;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", s.className, className)} data-testid="status-pill" data-status={status}>
      <s.Icon className="size-3.5" aria-hidden /> {s.label}
    </span>
  );
}
