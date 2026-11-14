import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Stat tile: label · value · delta vs the previous period, colored by direction × whether up is good, always with an arrow and words. */
export function StatTile({ label, value, current, previous, upIsGood = true, format, hint, hero = false, comparison = "previous period" }: {
  label: string; value: string; current?: number; previous?: number | null; upIsGood?: boolean; format?: (n: number) => string; hint?: string; hero?: boolean; comparison?: string;
}) {
  let delta: React.ReactNode = null;
  if (current !== undefined && previous !== null && previous !== undefined) {
    const diff = current - previous;
    const good = diff === 0 ? null : (diff > 0) === upIsGood;
    const Icon = diff === 0 ? Minus : diff > 0 ? ArrowUpRight : ArrowDownRight;
    const pct = previous !== 0 ? ` (${diff > 0 ? "+" : ""}${Math.round((diff / Math.abs(previous)) * 100)}%)` : "";
    delta = (
      <p className={cn("flex items-center gap-1 text-xs", good === null ? "text-muted-foreground" : good ? "text-[var(--viz-up-good)]" : "text-[var(--viz-down-bad)]")} data-testid="stat-delta">
        <Icon className="size-3.5" aria-hidden />
        <span>{diff === 0 ? "No change" : `${diff > 0 ? "+" : "−"}${format ? format(Math.abs(diff)) : Math.abs(diff)}${pct}`} vs {comparison}</span>
      </p>
    );
  }
  return (
    <Card className={cn("gap-1 py-4", hero && "sm:col-span-2")} data-testid="stat-tile">
      <CardHeader><p className="text-sm text-muted-foreground">{label}</p></CardHeader>
      <CardContent className="space-y-1">
        <p className={cn("font-semibold tracking-tight", hero ? "text-5xl" : "text-2xl")}>{value}</p>
        {delta}
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
