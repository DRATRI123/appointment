"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { addDays, formatTime, toISODate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AvailabilitySummary, DayAvailability, Slot } from "@/types/booking";

export interface SlotPickerProps {
  serviceId: string;
  branchId: string;
  professionalId?: string;
  fetchDay: (params: { service_id: string; branch_id: string; date: string; professional_id?: string }) => Promise<DayAvailability>;
  fetchSummary: (params: { service_id: string; branch_id: string; from_date: string; to_date: string; professional_id?: string }) => Promise<AvailabilitySummary[]>;
  onSelect: (slot: Slot, day: DayAvailability) => void;
  selected?: Slot | null;
  startDate?: Date;
  daysVisible?: number;
}

export function SlotPicker({ serviceId, branchId, professionalId, fetchDay, fetchSummary, onSelect, selected, startDate = new Date(), daysVisible = 7 }: SlotPickerProps) {
  const [offset, setOffset] = useState(0);
  const [chosen, setDate] = useState<string | null>(null);
  const first = addDays(startDate, offset);
  const days = useMemo(() => Array.from({ length: daysVisible }, (_, i) => addDays(first, i)), [first, daysVisible]);
  const from = toISODate(days[0]);
  const to = toISODate(days[days.length - 1]);

  const summary = useQuery({
    queryKey: ["avail-summary", serviceId, branchId, professionalId, from, to],
    queryFn: () => fetchSummary({ service_id: serviceId, branch_id: branchId, from_date: from, to_date: to, professional_id: professionalId }),
  });
  // Until the customer picks a day, open the first day in view that has a free slot (late in the
  // evening "today" is usually full).
  const firstAvailable = summary.data?.find((d) => d.available)?.date;
  const date = chosen ?? firstAvailable ?? from;
  const day = useQuery({
    queryKey: ["avail-day", serviceId, branchId, professionalId, date],
    queryFn: () => fetchDay({ service_id: serviceId, branch_id: branchId, date, professional_id: professionalId }),
    enabled: chosen !== null || !summary.isLoading,
    refetchInterval: 30_000,
  });
  const summaryMap = new Map((summary.data ?? []).map((s) => [s.date, s]));

  return (
    <div className="space-y-4" data-testid="slot-picker">
      <div className="flex items-center gap-2">
        <Button type="button" size="icon" variant="outline" disabled={offset <= 0} onClick={() => setOffset((o) => Math.max(0, o - daysVisible))} aria-label="Earlier dates"><ChevronLeft /></Button>
        <div className="grid flex-1 grid-cols-7 gap-1">
          {days.map((d) => {
            const iso = toISODate(d);
            const s = summaryMap.get(iso);
            const disabled = s ? !s.available : false;
            return (
              <button
                key={iso}
                type="button"
                disabled={disabled}
                onClick={() => setDate(iso)}
                data-testid={`day-${iso}`}
                className={cn(
                  "flex flex-col items-center rounded-lg border px-1 py-2 text-xs transition-colors",
                  date === iso ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
                  disabled && "cursor-not-allowed opacity-40 hover:bg-transparent",
                )}
              >
                <span className="uppercase">{d.toLocaleDateString("en-IN", { weekday: "short" })}</span>
                <span className="text-base font-semibold">{d.getDate()}</span>
                <span className={cn("text-[10px]", date === iso ? "text-primary-foreground/80" : "text-muted-foreground")}>{s ? (s.available ? `${s.slot_count} slots` : "—") : summary.isLoading ? "…" : ""}</span>
              </button>
            );
          })}
        </div>
        <Button type="button" size="icon" variant="outline" onClick={() => setOffset((o) => o + daysVisible)} aria-label="Later dates"><ChevronRight /></Button>
      </div>

      {day.isLoading || (chosen === null && summary.isLoading) ? (
        <Skeleton className="h-32" />
      ) : !day.data || day.data.professionals.every((p) => p.slots.length === 0) ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">No free slots on this day. Try another date.</p>
      ) : (
        <div className="space-y-4">
          {day.data.professionals.filter((p) => p.slots.length).map((p) => (
            <div key={p.professional_id}>
              {day.data!.professionals.length > 1 ? <p className="mb-2 text-sm font-medium">{p.display_name}</p> : null}
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
                {p.slots.map((slot) => {
                  const active = selected?.start_at === slot.start_at && selected?.professional_id === slot.professional_id;
                  return (
                    <button
                      key={slot.start_at + slot.professional_id}
                      type="button"
                      data-testid="slot"
                      onClick={() => onSelect(slot, day.data!)}
                      className={cn("rounded-lg border px-2 py-2 text-sm font-medium transition-colors hover:border-primary hover:bg-accent", active && "border-primary bg-primary text-primary-foreground hover:bg-primary")}
                    >
                      {formatTime(slot.start_at, day.data!.timezone)}
                      {slot.remaining > 1 ? <span className="block text-[10px] font-normal opacity-70">{slot.remaining} left</span> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">Times shown in {day.data.timezone}.</p>
        </div>
      )}
    </div>
  );
}
