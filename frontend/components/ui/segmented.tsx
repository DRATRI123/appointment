"use client";

import { cn } from "@/lib/utils";

/**
 * A filter switch that looks like tabs but is a group of toggle buttons (aria-pressed). Use it when choosing an
 * option re-filters the content below instead of revealing a separate tab panel.
 */
export function Segmented<T extends string>({ value, onChange, options, label, className }: {
  value: T; onChange: (v: T) => void; options: readonly (readonly [T, string])[]; label: string; className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex h-10 w-fit items-center rounded-lg bg-muted p-1 text-muted-foreground", className)}>
      {options.map(([v, text]) => (
        <button key={`${v}-${text}`} type="button" aria-pressed={value === v} data-state={value === v ? "active" : "inactive"} onClick={() => onChange(v)}
          className="inline-flex h-8 items-center justify-center rounded-md px-3 text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm">
          {text}
        </button>
      ))}
    </div>
  );
}
