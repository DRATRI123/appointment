"use client";

import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { BusinessHours } from "@/types/catalog";

const DAYS: [string, string][] = [
  ["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"],
];

export function BusinessHoursEditor({ value, onChange, disabled }: { value: BusinessHours; onChange: (v: BusinessHours) => void; disabled?: boolean }) {
  const set = (day: string, windows: [string, string][] | null) => {
    const next = { ...value };
    if (windows === null) delete next[day];
    else next[day] = windows;
    onChange(next);
  };
  return (
    <div className="divide-y rounded-lg border">
      {DAYS.map(([key, label]) => {
        const windows = value[key];
        const open = Array.isArray(windows);
        return (
          <div key={key} className="flex flex-wrap items-start gap-3 px-3 py-2">
            <div className="flex w-36 items-center gap-2 pt-1.5">
              <Switch checked={open} disabled={disabled} onCheckedChange={(v) => set(key, v ? [["09:00", "17:00"]] : null)} aria-label={`${label} open`} />
              <span className="text-sm font-medium">{label}</span>
            </div>
            <div className="flex flex-1 flex-col gap-2">
              {open ? (
                windows.map(([start, end], i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input type="time" className="w-32" value={start} disabled={disabled} onChange={(e) => { const w = windows.map((x) => [...x] as [string, string]); w[i][0] = e.target.value; set(key, w); }} />
                    <span className="text-xs text-muted-foreground">to</span>
                    <Input type="time" className="w-32" value={end} disabled={disabled} onChange={(e) => { const w = windows.map((x) => [...x] as [string, string]); w[i][1] = e.target.value; set(key, w); }} />
                    {windows.length > 1 && !disabled ? (
                      <Button type="button" size="icon" variant="ghost" onClick={() => set(key, windows.filter((_, j) => j !== i))} aria-label="Remove window"><X /></Button>
                    ) : null}
                  </div>
                ))
              ) : (
                <span className="pt-1.5 text-sm text-muted-foreground">Closed</span>
              )}
              {open && !disabled ? (
                <Button type="button" size="sm" variant="ghost" className="w-fit" onClick={() => set(key, [...windows, ["16:00", "20:00"]])}><Plus /> Add window</Button>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
