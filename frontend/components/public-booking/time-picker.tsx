"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Moon, Sun, Sunrise } from "lucide-react";
import { publicBooking } from "@/services/booking";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { addDays, toISODate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DayAvailability, Slot } from "@/types/booking";

const WINDOW = 14;
const PARTS = [
  { key: "morning", label: "Morning", icon: Sunrise, test: (h: number) => h < 12 },
  { key: "afternoon", label: "Afternoon", icon: Sun, test: (h: number) => h >= 12 && h < 17 },
  { key: "evening", label: "Evening", icon: Moon, test: (h: number) => h >= 17 },
] as const;

function hourIn(iso: string, tz: string): number {
  return Number(new Intl.DateTimeFormat("en-GB", { hour: "2-digit", hour12: false, timeZone: tz }).format(new Date(iso)));
}

function timeLabel(iso: string, tz: string): string {
  return new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}

export function TimePicker({ slug, serviceId, branchId, professionalId, initialDate, busy, selected, onSelect }: {
  slug: string; serviceId: string; branchId: string; professionalId?: string; initialDate?: string; busy?: boolean;
  selected: Slot | null; onSelect: (slot: Slot, day: DayAvailability) => void;
}) {
  const today = useMemo(() => new Date(new Date().toDateString()), []);
  const startOffset = useMemo(() => {
    if (!initialDate) return 0;
    const diff = Math.round((new Date(`${initialDate}T00:00:00`).getTime() - today.getTime()) / 86_400_000);
    return diff > 0 && diff < 120 ? Math.floor(diff / WINDOW) * WINDOW : 0;
  }, [initialDate, today]);
  const [offset, setOffset] = useState(startOffset);
  const [chosen, setChosen] = useState<string | null>(initialDate ?? null);
  const days = useMemo(() => Array.from({ length: WINDOW }, (_, i) => addDays(today, offset + i)), [today, offset]);
  const from = toISODate(days[0]);
  const to = toISODate(days[days.length - 1]);
  const params = { service_id: serviceId, branch_id: branchId, professional_id: professionalId };

  const summary = useQuery({ queryKey: ["pb-summary", slug, serviceId, branchId, professionalId, from], queryFn: () => publicBooking.summary(slug, { ...params, from_date: from, to_date: to }) });
  const byDate = useMemo(() => new Map((summary.data ?? []).map((d) => [d.date, d])), [summary.data]);
  const firstOpen = summary.data?.find((d) => d.available)?.date;
  const date = chosen && (!byDate.size || byDate.get(chosen)?.available !== false) ? chosen : firstOpen ?? chosen ?? from;
  const day = useQuery({
    queryKey: ["pb-day", slug, serviceId, branchId, professionalId, date],
    queryFn: () => publicBooking.availability(slug, { ...params, date }),
    enabled: !summary.isLoading,
    refetchInterval: 30_000,
  });

  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    strip.current?.querySelector<HTMLElement>(`[data-date="${date}"]`)?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [date]);

  const tz = day.data?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const multiple = (day.data?.professionals.filter((p) => p.slots.length).length ?? 0) > 1;
  const noneInWindow = summary.isSuccess && !summary.data.some((d) => d.available);

  return (
    <div className="space-y-5" data-testid="slot-picker">
      <div className="flex items-center gap-2">
        <Button type="button" size="icon" variant="outline" className="hidden shrink-0 rounded-full bg-white sm:inline-flex" disabled={offset <= 0} onClick={() => setOffset((o) => Math.max(0, o - WINDOW))} aria-label="Earlier dates"><ChevronLeft /></Button>
        <div ref={strip} className="flex flex-1 snap-x gap-2 overflow-x-auto scroll-smooth py-1 [scrollbar-width:none]" role="listbox" aria-label="Choose a date">
          {days.map((d) => {
            const iso = toISODate(d);
            const s = byDate.get(iso);
            const open = s ? s.available : !summary.isSuccess;
            const active = date === iso;
            return (
              <button key={iso} type="button" role="option" aria-selected={active} data-date={iso} data-testid={`day-${iso}`} disabled={!open}
                onClick={() => setChosen(iso)}
                className={cn("flex w-[4.25rem] shrink-0 snap-start flex-col items-center gap-1 rounded-[1.25rem] border px-1 py-3 transition-all",
                  active ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-[0_10px_20px_-10px_color-mix(in_oklab,var(--primary)_80%,transparent)]" : "border-black/5 bg-white text-gray-900 shadow-sm hover:border-[var(--primary)]",
                  !open && "cursor-not-allowed opacity-40 shadow-none hover:border-black/5")}>
                <span className="text-[11px] font-medium uppercase tracking-wide">{d.toLocaleDateString("en-IN", { weekday: "short" })}</span>
                <span className="text-xl font-semibold leading-none">{d.getDate()}</span>
                <span className={cn("text-[11px]", active ? "text-[var(--primary-foreground)]" : "text-gray-500")}>
                  {s ? (s.available ? `${s.slot_count} open` : "Full") : summary.isLoading ? "…" : d.toLocaleDateString("en-IN", { month: "short" })}
                </span>
              </button>
            );
          })}
        </div>
        <Button type="button" size="icon" variant="outline" className="hidden shrink-0 rounded-full bg-white sm:inline-flex" onClick={() => setOffset((o) => o + WINDOW)} aria-label="Later dates"><ChevronRight /></Button>
      </div>

      {day.isLoading || summary.isLoading ? (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-11 rounded-xl" />)}</div>
      ) : day.isError ? (
        <p className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive-ink" role="alert">We couldn&apos;t load times. Please check your connection and try again.</p>
      ) : noneInWindow ? (
        <p className="rounded-2xl border border-dashed bg-background p-6 text-center text-sm text-muted-foreground" role="status">No free times in these two weeks. Try later dates with the arrow.</p>
      ) : !day.data || day.data.professionals.every((p) => p.slots.length === 0) ? (
        <p className="rounded-2xl border border-dashed bg-background p-6 text-center text-sm text-muted-foreground" role="status">No free times on this day. Please pick another date.</p>
      ) : (
        <div className={cn("space-y-5 transition-opacity", busy && "pointer-events-none opacity-60")} aria-busy={busy}>
          {day.data.professionals.filter((p) => p.slots.length).map((p) => (
            <div key={p.professional_id} className="space-y-3">
              {multiple ? <p className="text-sm font-semibold">{p.display_name}</p> : null}
              {PARTS.map((part) => {
                const slots = p.slots.filter((s) => part.test(hourIn(s.start_at, tz)));
                if (!slots.length) return null;
                const Icon = part.icon;
                return (
                  <div key={part.key} className="space-y-2">
                    <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground"><Icon className="size-3.5" aria-hidden />{part.label}</p>
                    <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 xl:grid-cols-5">
                      {slots.map((slot) => {
                        const active = selected?.start_at === slot.start_at && selected?.professional_id === slot.professional_id;
                        return (
                          <button key={slot.start_at + slot.professional_id} type="button" data-testid="slot" aria-pressed={active} onClick={() => onSelect(slot, day.data!)}
                            className={cn("rounded-full border border-black/10 bg-white px-2 py-2.5 text-sm font-semibold tabular-nums text-gray-800 transition-all hover:border-[var(--primary)]",
                              active && "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-[0_8px_18px_-8px_color-mix(in_oklab,var(--primary)_80%,transparent)] hover:border-[var(--primary)]")}>
                            {timeLabel(slot.start_at, tz)}
                            {slot.remaining > 1 ? <span className="block text-[10px] font-normal opacity-75">{slot.remaining} left</span> : null}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
          <p className="text-xs text-muted-foreground">Times are in the clinic&apos;s time zone ({day.data.timezone}).</p>
        </div>
      )}
    </div>
  );
}
